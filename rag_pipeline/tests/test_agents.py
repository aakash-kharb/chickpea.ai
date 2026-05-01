"""
test_agents.py
--------------
Unit tests for the Chickpea RAG Pipeline v3.
Tests use synthetic data (temp CSV files) — no live API calls.

Run: python -m pytest tests/test_agents.py -v

Modules tested:
  - semantic_router      (pattern-based fallback router)
  - ai_router            (AI-powered intent classifier, mocked LLM)
  - gene_search_agent    (gene list retrieval from Stress_Binary_Matrix)
  - gene_collector       (unified data collection — replaces old per-agent tests)
  - id_mapper            (Ca/LOC/symbol resolution)
"""

import json
import math
import os
import pytest
from pathlib import Path
from unittest.mock import patch

# ─────────────────────────────────────────────────────────────────────────────
# Synthetic CSV fixtures
# ─────────────────────────────────────────────────────────────────────────────

STRESS_CSV = """\
Ca_ID,Stress,Num_Stresses,Cold,Drought,Salinity,Heat
Ca_00001,"Drought, Salinity",2,0,1,1,0
Ca_00011,"Heat",1,0,0,0,1
Ca_00999,"Drought, Salinity, Heat",3,0,1,1,1
"""

STRESS_CSV_EXTENDED = """\
Ca_ID,Stress,Num_Stresses,Cold,Drought,Salinity,Heat
Ca_00011,"Heat",1,0,0,0,1
Ca_00100,"Cold, Drought",2,1,1,0,0
Ca_00200,"Cold",1,1,0,0,0
Ca_00300,"Cold, Drought, Heat",3,1,1,0,1
"""

SEQ_CSV = """\
Ca_ID,Peptide_Sequence
Ca_00001,MKVL
Ca_00011,MKNLIKGVKKLKLWSKKKRKKKDEQEKYEHTPPPPLTCHHHCCCSCSTTTHPSAPPLPPF
Ca_00999,MGNTSSFSCIPNCASVDICNTNGVKGIKKNTATLFDTNGNIREINLPVKSAELMIELIGH
"""

EXPR_CSV_COLD = """\
Gene_identifier,Root-Control,Root-CS,Shoot-Control,Shoot-CS
Ca_00001,10.0,20.0,5.0,2.5
Ca_00011,0.0,0.0,3.0,6.0
Ca_00999,1.0,1.0,0.0,0.0
"""

MAPPING_CSV = """\
Transcript id,LOC id
Ca_00001,LOC101511858
Ca_00011,LOC101487945
Ca_00999,LOC101496284
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return str(p)


# ─────────────────────────────────────────────────────────────────────────────
# id_mapper tests
# ─────────────────────────────────────────────────────────────────────────────

from modules.id_mapper import resolve_to_ca, _load_mapping_tables


def test_id_mapper_ca_passthrough(tmp_path):
    """Ca_XXXXX inputs are accepted directly without CSV lookup."""
    mapping = _write(tmp_path, "mapping.csv", MAPPING_CSV)
    _load_mapping_tables.cache_clear()
    r = resolve_to_ca("Ca_00001", mapping)
    assert r["resolved"] is True
    assert r["was_ca"] is True
    assert r["ca_id"] == "Ca_00001"


def test_id_mapper_loc_to_ca(tmp_path):
    """LOC IDs are correctly resolved via CSV lookup (not digit-stripping)."""
    mapping = _write(tmp_path, "mapping.csv", MAPPING_CSV)
    _load_mapping_tables.cache_clear()
    r = resolve_to_ca("LOC101511858", mapping)
    assert r["resolved"] is True
    assert r["was_ca"] is False
    assert r["ca_id"] == "Ca_00001"    # from CSV, not digit manipulation
    assert r["external_id"] == "LOC101511858"


def test_id_mapper_unknown_id(tmp_path):
    """Unknown IDs are passed through unchanged with resolved=False."""
    mapping = _write(tmp_path, "mapping.csv", MAPPING_CSV)
    _load_mapping_tables.cache_clear()
    r = resolve_to_ca("BOGUS_GENE", mapping)
    assert r["resolved"] is False
    assert r["ca_id"] == "BOGUS_GENE"  # unchanged


def test_id_mapper_case_insensitive(tmp_path):
    """LOC lookup is case-insensitive."""
    mapping = _write(tmp_path, "mapping.csv", MAPPING_CSV)
    _load_mapping_tables.cache_clear()
    r = resolve_to_ca("loc101511858", mapping)
    assert r["resolved"] is True
    assert r["ca_id"] == "Ca_00001"


# ─────────────────────────────────────────────────────────────────────────────
# gene_collector tests  (replaces expression_agent / sequence_agent / stress_label_agent)
# ─────────────────────────────────────────────────────────────────────────────

from modules.gene_collector import (
    get_gene_packet, format_llm_context,
    RESPONSIVE, NOT_RESPONSIVE, UNKNOWN,
    _log2fc, _classify, LOG2FC_UP, LOG2FC_DOWN,
)


def test_log2fc_basic():
    """log2((stress+1)/(ctrl+1)) calculation."""
    fc = _log2fc("0.0", "10.0")
    assert fc is not None
    assert abs(fc - math.log2(11.0 / 1.0)) < 1e-6


def test_log2fc_nan_skipped():
    """Non-numeric values produce None (never imputed)."""
    assert _log2fc("", "5.0") is None
    assert _log2fc("n/a", "5.0") is None
    assert _log2fc("5.0", "") is None


def test_classify_upregulated():
    assert _classify(LOG2FC_UP) == "UPREGULATED"
    assert _classify(LOG2FC_UP + 1) == "UPREGULATED"


def test_classify_downregulated():
    assert _classify(LOG2FC_DOWN) == "DOWNREGULATED"
    assert _classify(LOG2FC_DOWN - 1) == "DOWNREGULATED"


def test_classify_not_significant():
    assert _classify(0.0) == "NOT_SIGNIFICANT"
    assert _classify(LOG2FC_UP - 0.01) == "NOT_SIGNIFICANT"


def _make_collector_dirs(tmp_path):
    """Create minimal data dir structure for gene_collector tests."""
    indiv = tmp_path / "Individual Files"
    indiv.mkdir()
    (indiv / "Cold_Top.csv").write_text(EXPR_CSV_COLD)

    pep  = tmp_path / "Ca_Peptide_Sequences.csv"
    pep.write_text(SEQ_CSV)

    stress = tmp_path / "Stress_Binary_Matrix.csv"
    stress.write_text(STRESS_CSV)

    mapping = tmp_path / "mapping.csv"
    mapping.write_text(MAPPING_CSV)

    return indiv, pep, stress, mapping


def test_collector_expression_found(tmp_path):
    """Gene with expression data gets pairs collected."""
    from modules.gene_collector import _load_expr_file
    _load_expr_file.cache_clear()
    from modules.id_mapper import _load_mapping_tables
    _load_mapping_tables.cache_clear()

    indiv, pep, stress, mapping = _make_collector_dirs(tmp_path)
    p = get_gene_packet("Ca_00001", indiv_dir=indiv, peptide_csv=pep,
                        stress_csv=stress, mapping_csv=mapping)
    assert len(p.expression) > 0
    assert p.files_with_gene > 0


def test_collector_peptide_found(tmp_path):
    """Peptide lookup is independent of expression data."""
    from modules.gene_collector import _load_expr_file
    _load_expr_file.cache_clear()
    from modules.id_mapper import _load_mapping_tables
    _load_mapping_tables.cache_clear()

    indiv, pep, stress, mapping = _make_collector_dirs(tmp_path)
    p = get_gene_packet("Ca_00001", indiv_dir=indiv, peptide_csv=pep,
                        stress_csv=stress, mapping_csv=mapping)
    assert p.peptide is not None
    assert "MKVL" in p.peptide


def test_collector_three_state_responsive(tmp_path):
    """Gene in Individual Files AND in matrix with label=1 → RESPONSIVE."""
    from modules.gene_collector import _load_expr_file
    _load_expr_file.cache_clear()
    from modules.id_mapper import _load_mapping_tables
    _load_mapping_tables.cache_clear()

    indiv, pep, stress, mapping = _make_collector_dirs(tmp_path)
    p = get_gene_packet("Ca_00999", indiv_dir=indiv, peptide_csv=pep,
                        stress_csv=stress, mapping_csv=mapping)
    assert p.stress_states["Drought"] == RESPONSIVE
    assert p.stress_states["Cold"] == NOT_RESPONSIVE
    assert p.in_stress_matrix is True


def test_collector_three_state_unknown(tmp_path):
    """Gene absent from Individual Files → UNKNOWN for all stresses."""
    from modules.gene_collector import _load_expr_file
    _load_expr_file.cache_clear()
    from modules.id_mapper import _load_mapping_tables
    _load_mapping_tables.cache_clear()

    # Ca_99999 is not in any of the synthetic CSVs
    indiv, pep, stress, mapping = _make_collector_dirs(tmp_path)
    p = get_gene_packet("Ca_99999", indiv_dir=indiv, peptide_csv=pep,
                        stress_csv=stress, mapping_csv=mapping)
    assert p.files_with_gene == 0
    assert all(v == UNKNOWN for v in p.stress_states.values())
    assert p.in_stress_matrix is False


def test_collector_loc_resolution(tmp_path):
    """LOC ID input is resolved to Ca_XXXXX before data lookup."""
    from modules.gene_collector import _load_expr_file
    _load_expr_file.cache_clear()
    from modules.id_mapper import _load_mapping_tables
    _load_mapping_tables.cache_clear()

    indiv, pep, stress, mapping = _make_collector_dirs(tmp_path)
    # LOC101511858 maps to Ca_00001 in the synthetic mapping CSV
    p = get_gene_packet("LOC101511858", indiv_dir=indiv, peptide_csv=pep,
                        stress_csv=stress, mapping_csv=mapping)
    assert p.gene_id == "Ca_00001"
    assert p.input_id == "LOC101511858"
    assert p.id_resolved is True
    assert len(p.expression) > 0   # data was found using the resolved ID


def test_collector_format_llm_context(tmp_path):
    """format_llm_context returns a non-empty string with gene ID."""
    from modules.gene_collector import _load_expr_file
    _load_expr_file.cache_clear()
    from modules.id_mapper import _load_mapping_tables
    _load_mapping_tables.cache_clear()

    indiv, pep, stress, mapping = _make_collector_dirs(tmp_path)
    p = get_gene_packet("Ca_00001", indiv_dir=indiv, peptide_csv=pep,
                        stress_csv=stress, mapping_csv=mapping)
    text = format_llm_context(p)
    assert isinstance(text, str)
    assert "Ca_00001" in text
    assert "Stress Matrix" in text


# ─────────────────────────────────────────────────────────────────────────────
# semantic_router tests
# ─────────────────────────────────────────────────────────────────────────────

from modules.semantic_router import route_query


def test_router_gene_id_extraction():
    result = route_query("What is the expression of Ca_00001 under drought?")
    assert "Ca_00001" in result["gene_ids"]


def test_router_expression_intent():
    result = route_query("Is Ca_00999 upregulated under stress?")
    assert "expression" in result["agents"] or "stress_label" in result["agents"]


def test_router_sequence_intent():
    result = route_query("Show me the peptide sequence for Ca_00011")
    assert "sequence" in result["agents"]


def test_router_full_pipeline_fallback():
    result = route_query("Tell me everything about Ca_00011")
    assert "expression" in result["agents"]
    assert "sequence" in result["agents"]


def test_router_no_gene_id():
    result = route_query("What is the overall expression pattern?")
    assert result["gene_ids"] == []


# ─────────────────────────────────────────────────────────────────────────────
# ai_router tests  (mocked LLM — no API calls)
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_router_gene_list_query():
    """GENE_LIST intent with stress/n_genes extracted correctly."""
    mock_response = json.dumps({
        "intent": "GENE_LIST",
        "gene_ids": [],
        "agents": ["stress_label", "gene_search"],
        "stress_filter": "Cold",
        "regulation_filter": None,
        "n_genes_requested": 3,
        "output_format": "COMPACT_LIST",
        "required_sections": ["Summary", "Stress Classification", "Biological Insights"],
        "token_budget": "MEDIUM",
        "router_note": "User wants list of cold genes",
    })
    with patch("modules.llm_interface.get_llm_response_with_model", return_value=mock_response), \
         patch("modules.llm_interface.get_llm_response", return_value=mock_response):
        from modules import ai_router
        result = ai_router.route_query_ai("give me 3 cold resistant genes")
        assert result["intent"] == "GENE_LIST"
        assert result["stress_filter"] == "Cold"
        assert result["n_genes_requested"] == 3
        assert result["output_format"] == "COMPACT_LIST"
        assert "routing_capsule" in result


def test_ai_router_single_gene_profile():
    """GENE_PROFILE intent extracts Ca_00011."""
    mock_response = json.dumps({
        "intent": "GENE_PROFILE",
        "gene_ids": ["Ca_00011"],
        "agents": ["expression", "sequence", "stress_label"],
        "stress_filter": None,
        "regulation_filter": None,
        "n_genes_requested": None,
        "output_format": "FULL_PROFILE",
        "required_sections": ["Summary", "Expression Evidence", "Stress Classification",
                              "Sequence Analysis", "Confidence Assessment", "Biological Insights"],
        "token_budget": "LONG",
        "router_note": "Single gene profile",
    })
    with patch("modules.llm_interface.get_llm_response_with_model", return_value=mock_response), \
         patch("modules.llm_interface.get_llm_response", return_value=mock_response):
        from modules import ai_router
        result = ai_router.route_query_ai("Is Ca_00011 upregulated under heat?")
        assert "Ca_00011" in result["gene_ids"]
        assert result["output_format"] == "FULL_PROFILE"


def test_ai_router_out_of_scope():
    """OUT_OF_SCOPE intent returns immediately without agents."""
    mock_response = json.dumps({
        "intent": "OUT_OF_SCOPE",
        "gene_ids": [],
        "agents": [],
        "stress_filter": None,
        "regulation_filter": None,
        "n_genes_requested": None,
        "output_format": "NONE",
        "required_sections": [],
        "token_budget": "SHORT",
        "router_note": "Math question — out of scope",
    })
    with patch("modules.llm_interface.get_llm_response_with_model", return_value=mock_response), \
         patch("modules.llm_interface.get_llm_response", return_value=mock_response):
        from modules import ai_router
        result = ai_router.route_query_ai("what is 5 times 59?")
        assert result["intent"] == "OUT_OF_SCOPE"
        assert result["agents"] == []
        assert "out_of_scope_response" in result


def test_ai_router_fallback_on_bad_json():
    """Falls back to semantic_router gracefully on malformed JSON."""
    with patch("modules.llm_interface.get_llm_response_with_model", return_value="not json!"), \
         patch("modules.llm_interface.get_llm_response", return_value="not json!"):
        from modules import ai_router
        result = ai_router.route_query_ai("Is Ca_00011 upregulated under heat?")
        assert "gene_ids" in result
        assert "agents" in result
        assert "stress_filter" in result


def test_ai_router_regex_catches_missed_id():
    """Gene ID in query is captured by regex even if LLM missed it."""
    mock_response = json.dumps({
        "intent": "EXPRESSION",
        "gene_ids": [],          # LLM forgot to extract
        "agents": ["expression"],
        "stress_filter": "Drought",
        "regulation_filter": None,
        "n_genes_requested": None,
        "output_format": "FOCUSED",
        "required_sections": ["Summary", "Expression Evidence"],
        "token_budget": "MEDIUM",
        "router_note": "expression check",
    })
    with patch("modules.llm_interface.get_llm_response_with_model", return_value=mock_response), \
         patch("modules.llm_interface.get_llm_response", return_value=mock_response):
        from modules import ai_router
        result = ai_router.route_query_ai("Is Ca_00999 downregulated under drought?")
        assert any("00999" in g for g in result["gene_ids"])


# ─────────────────────────────────────────────────────────────────────────────
# gene_search_agent tests
# ─────────────────────────────────────────────────────────────────────────────

from modules.gene_search_agent import search_genes, _load_stress_matrix as _gsm_load


def test_gene_search_cold_filter(tmp_path):
    """Only cold-labelled genes are returned for stress_filter='Cold'."""
    path = _write(tmp_path, "stress_ext.csv", STRESS_CSV_EXTENDED)
    _gsm_load.cache_clear()

    result = search_genes(stress_filter="Cold", n_genes=10, stress_matrix_path=path)
    assert result["found"] is True
    returned_ids = [g["gene_id"] for g in result["genes"]]
    assert "CA_00011" not in returned_ids   # Heat only — must not appear
    assert "CA_00100" in returned_ids
    assert "CA_00200" in returned_ids
    assert "CA_00300" in returned_ids


def test_gene_search_no_filter_returns_all(tmp_path):
    """No stress_filter returns all genes."""
    path = _write(tmp_path, "stress_ext.csv", STRESS_CSV_EXTENDED)
    _gsm_load.cache_clear()

    result = search_genes(stress_filter=None, n_genes=100, stress_matrix_path=path)
    assert result["total_matched"] == 4


def test_gene_search_nonexistent_stress(tmp_path):
    """A stress type not in any gene returns found=False."""
    csv = "Ca_ID,Stress,Num_Stresses,Cold,Drought,Salinity,Heat\nCa_00001,\"Heat\",1,0,0,0,1\n"
    path = _write(tmp_path, "stress_only_heat.csv", csv)
    _gsm_load.cache_clear()

    result = search_genes(stress_filter="Cold", n_genes=5, stress_matrix_path=path)
    assert result["found"] is False
    assert result["total_matched"] == 0


def test_gene_search_n_genes_respected(tmp_path):
    """Result list is capped at n_genes."""
    path = _write(tmp_path, "stress_ext.csv", STRESS_CSV_EXTENDED)
    _gsm_load.cache_clear()

    result = search_genes(stress_filter=None, n_genes=2, stress_matrix_path=path)
    assert len(result["genes"]) <= 2


def test_gene_search_sorted_by_num_stresses(tmp_path):
    """Multi-stress genes appear first (sorted by Num_Stresses desc)."""
    path = _write(tmp_path, "stress_ext.csv", STRESS_CSV_EXTENDED)
    _gsm_load.cache_clear()

    result = search_genes(stress_filter="Cold", n_genes=10, stress_matrix_path=path)
    num_stresses = [g["num_stresses"] for g in result["genes"]]
    assert num_stresses == sorted(num_stresses, reverse=True)
