"""
gene_collector.py — v2 (correct three-state stress classification)
-------------------------------------------------------------------
Unified data collector for the Chickpea Stress-Gene RAG pipeline.

THREE-STATE STRESS CLASSIFICATION (corrected semantics)
═══════════════════════════════════════════════════════
Data flow:
  Raw RNA-seq data → Individual Files (33,351 unique Ca IDs)
                         ↓ (threshold test)
                   Stress_Binary_Matrix (1,630 genes — at least one DE stress)

State          | Condition                                         | Meaning
───────────────┼───────────────────────────────────────────────────┼──────────────────────────────────────────
RESPONSIVE     | In Individual Files AND in matrix with label=1    | Confirmed DE responder for this stress
NOT_RESPONSIVE | In Individual Files AND (label=0 in matrix        | Expression recorded; below DE threshold
               |   OR not in matrix at all)                        |
UNKNOWN        | NOT in Individual Files                           | No expression data recorded at all
               |   (gap in Ca_XXXXX sequence — experimental miss)  | Cannot say responsive or not

KEY POINT: Peptide sequence is completely independent data.
A gene can be UNKNOWN for stress (absent from Individual Files)
yet still have a sequence in Ca_Peptide_Sequences.csv.

Retrieval steps:
  ① ID resolution  — Ca_XXXXX / LOC… / ARF1 / NAC01 → canonical Ca_ID via mapping.csv
  ② Expression     — all 14 individual stress CSVs, Log2FC calculation, UP/DOWN labeling
  ③ Peptide        — Ca_Peptide_Sequences.csv (completely independent lookup)
  ④ Stress states  — three-state classification using BOTH expression presence AND binary matrix
"""

from __future__ import annotations

import math
import csv
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

# ── Defaults ───────────────────────────────────────────────────────────────────
_MODULE_DIR      = Path(__file__).resolve().parent
_PROJECT_ROOT    = _MODULE_DIR.parents[1]

_DEFAULT_INDIV_DIR   = _PROJECT_ROOT / "Individual Files"
_DEFAULT_PEPTIDE     = _PROJECT_ROOT / "Ca_Peptide_Sequences.csv"
_DEFAULT_STRESS_MAT  = _PROJECT_ROOT / "Stress_Binary_Matrix.csv"
_DEFAULT_MAPPING     = _PROJECT_ROOT / "mapping.csv"
_DEFAULT_BIOCHEM     = _PROJECT_ROOT / "BiochemicalProperties.csv"

# ── Thresholds ─────────────────────────────────────────────────────────────────
LOG2FC_UP   =  1.5
LOG2FC_DOWN = -1.5

# ── Three stress states ────────────────────────────────────────────────────────
RESPONSIVE     = "RESPONSIVE"       # binary label = 1
NOT_RESPONSIVE = "NOT_RESPONSIVE"   # binary label = 0 (observed but below threshold)
UNKNOWN        = "UNKNOWN"          # absent from matrix (no classification possible)

# ── GEO Accession IDs per stress (data provenance) ────────────────────────────
# Source: FilesExtraInfoNotesComment.txt
GEO_ACCESSIONS: dict[str, list[str]] = {
    "HEAT":     ["PRJNA748749"],
    "COLD":     ["GSE53711"],
    "DROUGHT":  ["GSE53711", "GSE104609", "GSE193077"],
    "SALINITY": ["GSE53711", "GSE70377", "GSE110127", "GSE204727"],
}

# Map each CSV filename → its GEO/BioProject accession for the Source column
FILE_TO_GEO: dict[str, str] = {
    "SalinityRootShoot53711_Top.csv": "GSE53711",
    "SalinityGSE70377_Top.csv":      "GSE70377",
    "Salinity_ICCV_JG_Top.csv":      "GSE110127",
    "SalinityICCV2-JG62_Top.csv":    "GSE204727",
    "Cold_Top.csv":                  "GSE53711",
    "Drought_53711_Top.csv":         "GSE53711",
    "DroughtICC4958-1882_Top.csv":   "GSE104609",
    "Drought_ICC2861-283_Top.csv":   "GSE193077",
    "Cultivar_92944_filtered.csv":   "PRJNA748749",
    "Cultivar_15614_filtered.csv":   "PRJNA748749",
    "Cultivar_10685_filtered.csv":   "PRJNA748749",
    "Cultivar_5912_filtered.csv":    "PRJNA748749",
    "Cultivar_4567_filtered.csv":    "PRJNA748749",
    "Cultivar_1356_filtered.csv":    "PRJNA748749",
    "HEAT_merged_Top.csv":           "PRJNA748749",
}

# ── Expression file registry ──────────────────────────────────────────────────
_FILE_REGISTRY: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
    # (filename, stress_type, gene_col_hint, [(ctrl_col, stress_col, tissue_label), …])
    # ── SALINITY ────────────────────────────────────────────────────────────────
    ("SalinityRootShoot53711_Top.csv", "SALINITY", "Gene_identifier", [
        ("Root-Control",  "Root-SS",   "Root tissue"),
        ("Shoot-Control", "Shoot-SS",  "Shoot tissue"),
    ]),
    ("SalinityGSE70377_Top.csv", "SALINITY", "Ref_gene_id", [
        ("Stol-veg-CT_FPKM",  "Stol-veg-SS_FPKM",  "Tolerant — Vegetative"),
        ("Ssen-veg-CT_FPKM",  "Ssen-veg-SS_FPKM",  "Sensitive — Vegetative"),
        ("Stol-rep-CT_FPKM",  "Stol-rep-SS_FPKM",  "Tolerant — Reproductive"),
        ("Ssen-rep-CT_FPKM",  "Ssen-rep-SS_FPKM",  "Sensitive — Reproductive"),
    ]),
    ("Salinity_ICCV_JG_Top.csv", "SALINITY", "Ca IDS", [
        ("ICCV_Control",  "ICCV_Stress",  "ICCV leaf (normal)"),
        ("ICCV_LControl", "ICCV_LStress", "ICCV leaf (late)"),
        ("JG_Control",    "JG_Stress",    "JG62 leaf (normal)"),
        ("JG_LControl",   "JG_LStress",   "JG62 leaf (late)"),
    ]),
    ("SalinityICCV2-JG62_Top.csv", "SALINITY", "gene", [
        ("FPKM-SS-C", "FPKM-SS-S", "Shoot"),
        ("FPKM-ST-C", "FPKM-ST-S", "Root"),
    ]),
    # ── COLD ────────────────────────────────────────────────────────────────────
    ("Cold_Top.csv", "COLD", "Gene_identifier", [
        ("Root-Control",  "Root-CS",   "Root tissue"),
        ("Shoot-Control", "Shoot-CS",  "Shoot tissue"),
    ]),
    # ── DROUGHT ─────────────────────────────────────────────────────────────────
    ("Drought_53711_Top.csv", "DROUGHT", "Gene_identifier", [
        ("Root-Control",  "Root-DS",   "Root tissue"),
        ("Shoot-Control", "Shoot-DS",  "Shoot tissue"),
    ]),
    ("DroughtICC4958-1882_Top.csv", "DROUGHT", "gene", [
        ("FPKM-DS-C", "FPKM-DS-D", "Shoot — Drought-Sensitive"),
        ("FPKM-DT-C", "FPKM-DT-D", "Shoot — Drought-Tolerant"),
    ]),
    ("Drought_ICC2861-283_Top.csv", "DROUGHT", "Ca ids", [
        ("ICC2861_Control", "ICC2861_Stress", "ICC2861 cultivar"),
        ("ICC283_Control",  "ICC283_Stress",  "ICC283 cultivar"),
    ]),
    # ── HEAT (6 cultivars — PRJNA748749) ────────────────────────────────────────
    ("Cultivar_92944_filtered.csv", "HEAT", "Ca_ID", [
        ("92944_AFL_C", "92944_AFL_S", "ICCV 92944 — Leaf Reproductive"),
        ("92944_AFR_C", "92944_AFR_S", "ICCV 92944 — Root Reproductive"),
        ("92944_BFL_C", "92944_BFL_S", "ICCV 92944 — Leaf Vegetative"),
        ("92944_BFR_C", "92944_BFR_S", "ICCV 92944 — Root Vegetative"),
    ]),
    ("Cultivar_15614_filtered.csv", "HEAT", "Ca_ID", [
        ("15614_AFL_C", "15614_AFL_S", "ICC 15614 — Leaf Reproductive"),
        ("15614_AFR_C", "15614_AFR_S", "ICC 15614 — Root Reproductive"),
        ("15614_BFL_C", "15614_BFL_S", "ICC 15614 — Leaf Vegetative"),
        ("15614_BFR_C", "15614_BFR_S", "ICC 15614 — Root Vegetative"),
    ]),
    ("Cultivar_10685_filtered.csv", "HEAT", "Ca_ID", [
        ("10685_AFL_C", "10685_AFL_S", "ICC 10685 — Leaf Reproductive"),
        ("10685_AFR_C", "10685_AFR_S", "ICC 10685 — Root Reproductive"),
        ("10685_BFL_C", "10685_BFL_S", "ICC 10685 — Leaf Vegetative"),
        ("10685_BFR_C", "10685_BFR_S", "ICC 10685 — Root Vegetative"),
    ]),
    ("Cultivar_5912_filtered.csv", "HEAT", "Ca_ID", [
        ("5912_AFL_C", "5912_AFL_S", "ICC 5912 — Leaf Reproductive"),
        ("5912_AFR_C", "5912_AFR_S", "ICC 5912 — Root Reproductive"),
        ("5912_BFL_C", "5912_BFL_S", "ICC 5912 — Leaf Vegetative"),
        ("5912_BFR_C", "5912_BFR_S", "ICC 5912 — Root Vegetative"),
    ]),
    ("Cultivar_4567_filtered.csv", "HEAT", "Ca_ID", [
        ("4567_AFL_C", "4567_AFL_S", "ICC 4567 — Leaf Reproductive"),
        ("4567_AFR_C", "4567_AFR_S", "ICC 4567 — Root Reproductive"),
        ("4567_BFL_C", "4567_BFL_S", "ICC 4567 — Leaf Vegetative"),
        ("4567_BFR_C", "4567_BFR_S", "ICC 4567 — Root Vegetative"),
    ]),
    ("Cultivar_1356_filtered.csv", "HEAT", "Ca_ID", [
        ("1356_AFL_C", "1356_AFL_S", "ICC 1356 — Leaf Reproductive"),
        ("1356_AFR_C", "1356_AFR_S", "ICC 1356 — Root Reproductive"),
        ("1356_BFL_C", "1356_BFL_S", "ICC 1356 — Leaf Vegetative"),
        ("1356_BFR_C", "1356_BFR_S", "ICC 1356 — Root Vegetative"),
    ]),
]


# ── Data classes ───────────────────────────────────────────────────────────────
@dataclass
class ExpressionPair:
    stress:       str
    source_file:  str
    tissue:       str
    ctrl_fpkm:    float
    stress_fpkm:  float
    log2fc:       float
    regulation:   str    # UPREGULATED | DOWNREGULATED | NOT_SIGNIFICANT


@dataclass
class StressSummary:
    stress:     str
    avg_log2fc: float
    n_up:       int
    n_down:     int
    n_total:    int
    consensus:  str    # UPREGULATED | DOWNREGULATED | MIXED/NOT_SIGNIFICANT
    confidence: str    # HIGH (≥2 pairs) | LOW


@dataclass
class GenePacket:
    """All retrieved data for one gene — ready for LLM injection."""
    gene_id:          str
    input_id:         str                      # original query ID (may be LOC/symbol)
    external_id:      str = ""                 # LOC ID / gene symbol if mapped
    id_resolved:      bool = True              # False if mapping lookup failed
    id_note:          str = ""                 # from id_mapper

    expression:       list[ExpressionPair] = field(default_factory=list)
    stress_summary:   list[StressSummary]  = field(default_factory=list)
    nan_pairs:        int = 0
    files_checked:    int = 0
    files_with_gene:  int = 0

    peptide:          Optional[str] = None
    biochem_properties: Optional[dict] = None   # from BiochemicalProperties.csv

    # Three-state stress classification
    in_stress_matrix: bool = False           # True = gene exists in Stress Binary Matrix
    stress_labels:    dict = field(default_factory=dict)   # {stress: 0/1}
    stress_states:    dict = field(default_factory=dict)   # {stress: RESPONSIVE/NOT_RESPONSIVE/UNKNOWN}
    active_stresses:  list = field(default_factory=list)
    num_stresses:     int = 0
    stress_string:    str = ""

    errors:           list[str] = field(default_factory=list)


# ── File loading (cached per filepath) ────────────────────────────────────────
@lru_cache(maxsize=32)
def _load_expr_file(filepath: str, gene_col_hint: str) -> dict[str, dict[str, str]]:
    """
    Load one expression CSV.
    Returns dict keyed by UPPERCASE gene ID → {col_name: value}.
    gene_col_hint matched case-insensitively; falls back to column index 1.
    """
    with open(filepath, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        all_rows = list(reader)

    if not all_rows:
        return {}

    raw_headers = [c.strip() for c in all_rows[0]]

    gene_col_idx = next(
        (i for i, h in enumerate(raw_headers)
         if h.lower() == gene_col_hint.lower()),
        1 if len(raw_headers) >= 2 else 0,
    )

    result: dict[str, dict[str, str]] = {}
    for row in all_rows[1:]:
        padded = row + [""] * (len(raw_headers) - len(row))
        key = padded[gene_col_idx].strip().upper()
        if key:
            result[key] = {raw_headers[i]: padded[i].strip()
                           for i in range(len(raw_headers))}
    return result


# ── Math ───────────────────────────────────────────────────────────────────────
def _log2fc(ctrl_str: str, stress_str: str) -> Optional[float]:
    try:
        c, s = float(ctrl_str), float(stress_str)
        return math.log2((s + 1.0) / (c + 1.0))
    except (ValueError, TypeError):
        return None


def _classify(fc: float) -> str:
    if fc >= LOG2FC_UP:
        return "UPREGULATED"
    if fc <= LOG2FC_DOWN:
        return "DOWNREGULATED"
    return "NOT_SIGNIFICANT"


# ── Main collector ─────────────────────────────────────────────────────────────
def get_gene_packet(
    gene_id: str,
    indiv_dir:   Path = _DEFAULT_INDIV_DIR,
    peptide_csv: Path = _DEFAULT_PEPTIDE,
    stress_csv:  Path = _DEFAULT_STRESS_MAT,
    mapping_csv: Path = _DEFAULT_MAPPING,
    biochem_csv: Path = _DEFAULT_BIOCHEM,
) -> GenePacket:
    """
    Collect all data for one gene ID (Ca, LOC, or gene symbol).

    Steps:
      1. Resolve ID → canonical Ca_XXXXX via id_mapper
      2. Expression (all individual files, Log2FC)
      3. Peptide sequence
      4. Stress binary labels (three-state)
    """
    # ── Step 1: ID resolution ──────────────────────────────────────────────────
    from modules.id_mapper import resolve_to_ca
    mapping = resolve_to_ca(gene_id, str(mapping_csv))
    ca_id   = mapping["ca_id"]
    norm_id = ca_id.strip().upper()

    packet = GenePacket(
        gene_id     = ca_id,
        input_id    = mapping["input_id"],
        external_id = mapping["external_id"],
        id_resolved = mapping["resolved"],
        id_note     = mapping["note"],
    )

    # ── Step 2: Expression data ────────────────────────────────────────────────
    if indiv_dir.is_dir():
        for filename, stress_type, gene_col, pairs in _FILE_REGISTRY:
            fp = indiv_dir / filename
            if not fp.exists():
                continue
            packet.files_checked += 1
            try:
                rows_by_id = _load_expr_file(str(fp), gene_col)
            except Exception as exc:
                packet.errors.append(f"{filename}: {exc}")
                continue

            if norm_id not in rows_by_id:
                continue

            packet.files_with_gene += 1
            row = rows_by_id[norm_id]

            for ctrl_col, stress_col, tissue in pairs:
                fc = _log2fc(row.get(ctrl_col, ""), row.get(stress_col, ""))
                if fc is None:
                    packet.nan_pairs += 1
                    continue
                try:
                    ctrl_val   = float(row.get(ctrl_col,  "0") or 0)
                    stress_val = float(row.get(stress_col, "0") or 0)
                except ValueError:
                    packet.nan_pairs += 1
                    continue

                packet.expression.append(ExpressionPair(
                    stress      = stress_type,
                    source_file = filename,
                    tissue      = tissue,
                    ctrl_fpkm   = round(ctrl_val,   4),
                    stress_fpkm = round(stress_val, 4),
                    log2fc      = round(fc,          4),
                    regulation  = _classify(fc),
                ))

        # ── Per-stress summary ─────────────────────────────────────────────────
        buckets: dict[str, list[float]] = {}
        for ep in packet.expression:
            buckets.setdefault(ep.stress, []).append(ep.log2fc)

        for stress, vals in buckets.items():
            n    = len(vals)
            n_up = sum(1 for v in vals if v >= LOG2FC_UP)
            n_dn = sum(1 for v in vals if v <= LOG2FC_DOWN)
            avg  = round(sum(vals) / n, 4)
            if n_up > n_dn and n_up / n >= 0.5:
                consensus = "UPREGULATED"
            elif n_dn > n_up and n_dn / n >= 0.5:
                consensus = "DOWNREGULATED"
            else:
                consensus = "MIXED/NOT_SIGNIFICANT"
            packet.stress_summary.append(StressSummary(
                stress=stress, avg_log2fc=avg,
                n_up=n_up, n_down=n_dn, n_total=n,
                consensus=consensus,
                confidence="HIGH" if n >= 2 else "LOW",
            ))

    # ── Step 3: Peptide sequence ───────────────────────────────────────────────
    if peptide_csv.exists():
        try:
            with peptide_csv.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                for prow in reader:
                    rid = (prow.get("Ca_ID") or "").strip().upper()
                    if rid == norm_id:
                        seq = (prow.get("Peptide_Sequence") or "").strip()
                        packet.peptide = seq or None
                        break
        except Exception as exc:
            packet.errors.append(f"peptide_csv: {exc}")

    # ── Step 3b: Biochemical properties (pre-computed CSV) ────────────────────
    try:
        from modules.biochem_properties import lookup_biochem_properties, biochem_to_dict
        bp = lookup_biochem_properties(ca_id, csv_path=biochem_csv)
        if bp is not None:
            packet.biochem_properties = biochem_to_dict(bp)
    except Exception as exc:
        packet.errors.append(f"biochem_properties: {exc}")

    # ── Step 4: Three-state stress classification ─────────────────────────────
    # Gate 1: was the gene found in ANY Individual File?
    #   NO  → UNKNOWN for all stresses (no expression data whatsoever)
    #   YES → check Stress_Binary_Matrix for label
    #     • label = 1 → RESPONSIVE
    #     • label = 0 → NOT_RESPONSIVE (expression observed but below threshold)
    #     • not in matrix at all → NOT_RESPONSIVE (in files but didn't pass for any stress)
    _STRESS_COLS_ORDERED = ["Cold", "Drought", "Salinity", "Heat"]

    has_any_expression = packet.files_with_gene > 0

    if not has_any_expression:
        # Gene not in Individual Files → UNKNOWN for all
        packet.in_stress_matrix = False
        packet.stress_labels    = {}
        packet.stress_states    = {s: UNKNOWN for s in _STRESS_COLS_ORDERED}
        packet.active_stresses  = []
        packet.num_stresses     = 0
        packet.stress_string    = "No expression data recorded (UNKNOWN)"
    else:
        # Gene IS in Individual Files — look up binary matrix
        if stress_csv.exists():
            try:
                import csv as _csv_mod
                import pandas as _pd
                df = _pd.read_csv(str(stress_csv), dtype=str)
                df["Ca_ID"] = df["Ca_ID"].str.strip().str.upper()
                df = df.set_index("Ca_ID")

                stress_labels:  dict[str, int] = {}
                stress_states:  dict[str, str] = {}

                if norm_id in df.index:
                    packet.in_stress_matrix = True
                    row = df.loc[norm_id]
                    for s in _STRESS_COLS_ORDERED:
                        if s in df.columns:
                            try:
                                val = int(float(row[s]))
                            except (ValueError, TypeError):
                                val = 0
                            stress_labels[s] = val
                            stress_states[s] = RESPONSIVE if val == 1 else NOT_RESPONSIVE
                        else:
                            stress_states[s] = NOT_RESPONSIVE
                    # stress_string from matrix
                    stress_str = str(row.get("Stress", "")).strip() if "Stress" in df.columns else ""
                    active = [s for s, v in stress_labels.items() if v == 1]
                    try:
                        num = int(float(row.get("Num_Stresses", len(active))))
                    except (ValueError, TypeError):
                        num = len(active)
                    packet.stress_labels   = stress_labels
                    packet.active_stresses = active
                    packet.num_stresses    = num
                    packet.stress_string   = stress_str
                else:
                    # In Individual Files but NOT in Stress_Binary_Matrix
                    # → expression observed but didn't pass threshold for ANY stress
                    packet.in_stress_matrix = False
                    for s in _STRESS_COLS_ORDERED:
                        stress_states[s] = NOT_RESPONSIVE
                    packet.stress_labels   = {}
                    packet.active_stresses = []
                    packet.num_stresses    = 0
                    packet.stress_string   = "Expression recorded; below DE threshold for all stresses"

                packet.stress_states = stress_states

            except Exception as exc:
                packet.errors.append(f"stress_labels: {exc}")
                packet.stress_states = {s: NOT_RESPONSIVE for s in _STRESS_COLS_ORDERED}

    return packet


# ── Formatters ─────────────────────────────────────────────────────────────────
def _esc(v: str) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ").strip()


def format_llm_context(packet: GenePacket) -> str:
    """
    Compact plain-text context block for direct LLM injection.
    All signal, no noise.
    """
    gid = packet.gene_id
    lines = [f"=== Gene Data Packet: {gid} ==="]

    # ID resolution note
    if not packet.id_resolved or packet.input_id.upper() != gid.upper():
        lines.append(f"Input ID: {packet.input_id}  →  Resolved: {gid}  ({packet.id_note})")
    lines.append("")

    # ── Stress classification (three-state) ────────────────────────────────────
    if packet.in_stress_matrix:
        lines.append(f"Stress Matrix classification ({packet.num_stresses} stress(es) responsive):")
        _state_short = {RESPONSIVE: "1 ✓", NOT_RESPONSIVE: "0 ✗", UNKNOWN: "?"}
        for s in ("Cold", "Drought", "Salinity", "Heat"):
            state = packet.stress_states.get(s, UNKNOWN)
            lines.append(f"  {s:<10}: {_state_short[state]}  [{state}]")
    elif packet.files_with_gene > 0:
        lines.append("Stress Matrix: NOT LISTED (gene has expression data but did not pass")
        lines.append("  DE threshold for any stress — classified as NOT_RESPONSIVE for all.")
    else:
        lines.append("Stress Matrix: NOT APPLICABLE — gene absent from Individual Expression Files.")
        lines.append("  All four stresses are UNKNOWN (no expression data recorded).")
    lines.append("")

    # ── Expression data ────────────────────────────────────────────────────────
    if packet.expression:
        lines.append(f"Expression data — {len(packet.expression)} pairs across "
                     f"{packet.files_with_gene}/{packet.files_checked} files "
                     f"(Log2FC threshold ±{LOG2FC_UP}):")
        hdr = f"  {'Source':<12} {'Tissue':<34} {'Ctrl':>8} {'Stress':>8} {'Log2FC':>7}  Status"
        lines.append(hdr)
        lines.append("  " + "─" * (len(hdr) - 2))

        for ep in packet.expression:
            geo_id = FILE_TO_GEO.get(ep.source_file, ep.source_file)
            lines.append(
                f"  {geo_id:<12} {ep.tissue:<34} "
                f"{ep.ctrl_fpkm:>8.3f} {ep.stress_fpkm:>8.3f} "
                f"{ep.log2fc:>+7.3f}  {ep.regulation}"
            )
        lines.append("")

        lines.append("Per-stress summary:")
        for s in packet.stress_summary:
            lines.append(
                f"  {s.stress:<9}: avg={s.avg_log2fc:+.3f} | {s.consensus} | "
                f"↑{s.n_up} ↓{s.n_down} of {s.n_total} pairs | conf={s.confidence}"
            )
        if packet.nan_pairs:
            lines.append(f"  ({packet.nan_pairs} NaN pairs skipped — not imputed)")
    else:
        lines.append("Expression data: NOT FOUND in any individual expression file.")
        lines.append("  This means either:")
        lines.append("  (a) the gene is not in the top-expressed set for any stress experiment, or")
        lines.append("  (b) the gene ID format was not matched (check ID resolution note above).")
    lines.append("")

    # ── Peptide sequence ───────────────────────────────────────────────────────
    if packet.peptide:
        seq = packet.peptide
        n = len(seq)
        lines.append(f"Peptide ({n} aa):")
        lines.append("```")
        lines.append(seq)
        lines.append("```")
    else:
        lines.append("Peptide sequence: NOT FOUND")
    lines.append("")

    # ── Biochemical properties ─────────────────────────────────────────────────
    bp = packet.biochem_properties
    if bp:
        stability = "Stable" if bp["instability_index"] < 40 else "Unstable"
        lines.append("Biochemical Properties:")
        lines.append(f"  Total Amino Acids : {bp['total_amino_acids']}")
        lines.append(f"  Molecular Weight  : {bp['molecular_weight']:,.2f} Da")
        lines.append(f"  Theoretical pI    : {bp['theoretical_pi']:.2f}")
        lines.append(f"  Instability Index : {bp['instability_index']:.2f}  ({stability})")
        lines.append(f"  Aliphatic Index   : {bp['aliphatic_index']:.2f}")
        lines.append(f"  GRAVY             : {bp['gravy']:.4f}")
        lines.append(f"  Atomic Composition: C={bp['total_c_atoms']}  H={bp['total_h_atoms']}  "
                     f"N={bp['total_n_atoms']}  O={bp['total_o_atoms']}  S={bp['total_s_atoms']}")
    lines.append("")

    if packet.errors:
        lines.append(f"Retrieval errors ({len(packet.errors)}): " + " | ".join(packet.errors))
        lines.append("")

    lines.append("=" * max(30, len(f"=== Gene Data Packet: {gid} ===")))
    return "\n".join(lines)


def format_markdown(packet: GenePacket) -> str:
    """Full human-readable Markdown report for one gene."""
    gid   = packet.gene_id
    lines = []
    lines.append(f"# Gene Data Report — {gid}")
    if packet.external_id:
        lines.append(f"**External ID:** {packet.external_id}")
    if not packet.id_resolved:
        lines.append(f"> ⚠️ ID mapping not found for `{packet.input_id}`. Data searched using this ID as-is.")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    # ── Stress Classification ──────────────────────────────────────────────────
    lines.append("## Stress Classification")
    lines.append("")
    _interp = {
        RESPONSIVE:     "Significantly differentially expressed (passed Log2FC threshold)",
        NOT_RESPONSIVE: "Expression data recorded; did NOT pass Log2FC threshold",
        UNKNOWN:        "No expression data recorded — gene absent from Individual Files",
    }
    _emoji = {RESPONSIVE: "✅", NOT_RESPONSIVE: "❌", UNKNOWN: "❓"}

    if packet.in_stress_matrix:
        active = ", ".join(packet.active_stresses) or "None"
        lines.append(f"**Stress Matrix status:** Listed ✅")
        lines.append(f"**Responsive stresses ({packet.num_stresses}):** {active}")
        lines.append("")
        lines.append("| Stress | Label | State | Interpretation |")
        lines.append("| --- | :---: | --- | --- |")
        for s in ("Cold", "Drought", "Salinity", "Heat"):
            state = packet.stress_states.get(s, UNKNOWN)
            label = packet.stress_labels.get(s, "—")
            lines.append(f"| {s} | {label} | {_emoji[state]} {state} | {_interp[state]} |")
    elif packet.files_with_gene > 0:
        lines.append("**Stress Matrix status:** Not listed — expression recorded but below DE threshold")
        lines.append("")
        lines.append("> Expression data exists in Individual Files; gene did NOT pass the Log2FC")
        lines.append("> threshold needed for Stress Matrix inclusion. Classified as NOT_RESPONSIVE.")
        lines.append("")
        lines.append("| Stress | State | Interpretation |")
        lines.append("| --- | --- | --- |")
        for s in ("Cold", "Drought", "Salinity", "Heat"):
            lines.append(f"| {s} | ❌ NOT_RESPONSIVE | {_interp[NOT_RESPONSIVE]} |")
    else:
        lines.append("**Stress Matrix status:** Not applicable — gene absent from Individual Expression Files")
        lines.append("")
        lines.append("> This gene has no expression data recorded (UNKNOWN for all stresses).")
        lines.append("> It may still have a peptide sequence — that data is independent.")
        lines.append("")
        lines.append("| Stress | State | Interpretation |")
        lines.append("| --- | --- | --- |")
        for s in ("Cold", "Drought", "Salinity", "Heat"):
            lines.append(f"| {s} | ❓ UNKNOWN | {_interp[UNKNOWN]} |")
    lines.append("")

    # ── Expression Evidence ────────────────────────────────────────────────────
    lines.append("## Expression Evidence")
    if not packet.expression:
        lines.append("*No expression data found in Individual Files.*")
    else:
        by_stress: dict[str, list[ExpressionPair]] = {}
        for ep in packet.expression:
            by_stress.setdefault(ep.stress, []).append(ep)

        for stress, eps in by_stress.items():
            lines.append(f"### {stress.capitalize()} Stress")
            lines.append("")
            lines.append("| Source | Tissue / Genotype | Ctrl FPKM | Stress FPKM | Log2FC | Regulation |")
            lines.append("| --- | --- | ---: | ---: | ---: | --- |")
            for ep in eps:
                reg_emoji = {"UPREGULATED": "⬆️", "DOWNREGULATED": "⬇️"}.get(ep.regulation, "➡️")
                geo_id = FILE_TO_GEO.get(ep.source_file, ep.source_file)
                lines.append(
                    f"| {_esc(geo_id)} | {_esc(ep.tissue)} "
                    f"| {ep.ctrl_fpkm:.3f} | {ep.stress_fpkm:.3f} "
                    f"| {ep.log2fc:+.3f} | {reg_emoji} {ep.regulation} |"
                )
            lines.append("")

        lines.append("### Expression Summary")
        lines.append("")
        lines.append("| Stress | Avg Log2FC | Consensus | ↑ Up | ↓ Down | N Pairs | Confidence |")
        lines.append("| --- | ---: | --- | ---: | ---: | ---: | --- |")
        for s in packet.stress_summary:
            lines.append(
                f"| {s.stress} | {s.avg_log2fc:+.3f} | {s.consensus} "
                f"| {s.n_up} | {s.n_down} | {s.n_total} | {s.confidence} |"
            )
        if packet.nan_pairs:
            lines.append("")
            lines.append(f"*{packet.nan_pairs} pair(s) skipped — NaN/missing values (not imputed).*")
    lines.append("")

    # ── Peptide Sequence ───────────────────────────────────────────────────────
    lines.append("## Peptide Sequence")
    if packet.peptide:
        seq = packet.peptide
        n   = len(seq)
        lines.append(f"**Length:** {n} amino acids")
        lines.append("")
        lines.append("```")
        for i in range(0, len(seq), 60):
            lines.append(seq[i:i+60])
        lines.append("```")
        lines.append("")
    else:
        lines.append("*No peptide sequence found.*")
    lines.append("")

    # ── Biochemical Properties ─────────────────────────────────────────────────
    bp = packet.biochem_properties
    if bp:
        stability = "Stable" if bp["instability_index"] < 40 else "Unstable"
        lines.append("## Biochemical Properties")
        lines.append("")
        lines.append("| Property | Value |")
        lines.append("| --- | ---: |")
        lines.append(f"| Total Amino Acids | {bp['total_amino_acids']} |")
        lines.append(f"| Molecular Weight | {bp['molecular_weight']:,.2f} Da |")
        lines.append(f"| Theoretical pI | {bp['theoretical_pi']:.2f} |")
        lines.append(f"| Instability Index | {bp['instability_index']:.2f} ({stability}) |")
        lines.append(f"| Aliphatic Index | {bp['aliphatic_index']:.2f} |")
        lines.append(f"| GRAVY | {bp['gravy']:.4f} |")
        lines.append("")
        lines.append("### Atomic Composition")
        lines.append("")
        lines.append("| Atom | Count |")
        lines.append("| :---: | ---: |")
        lines.append(f"| C | {bp['total_c_atoms']} |")
        lines.append(f"| H | {bp['total_h_atoms']} |")
        lines.append(f"| N | {bp['total_n_atoms']} |")
        lines.append(f"| O | {bp['total_o_atoms']} |")
        lines.append(f"| S | {bp['total_s_atoms']} |")
        lines.append("")

    if packet.errors:
        lines.append("## Retrieval Errors")
        for e in packet.errors:
            lines.append(f"- `{e}`")
        lines.append("")

    return "\n".join(lines)


def packet_to_dict(packet: GenePacket) -> dict:
    """Serialisable dict — ready for JSON output or direct LLM pipeline injection."""
    return {
        "gene_id":          packet.gene_id,
        "input_id":         packet.input_id,
        "external_id":      packet.external_id,
        "id_resolved":      packet.id_resolved,
        "id_note":          packet.id_note,
        "in_stress_matrix": packet.in_stress_matrix,
        "stress_labels":    packet.stress_labels,
        "stress_states":    packet.stress_states,
        "active_stresses":  packet.active_stresses,
        "num_stresses":     packet.num_stresses,
        "stress_string":    packet.stress_string,
        "expression": [
            {
                "stress":       ep.stress,
                "source_file":  ep.source_file,
                "tissue":       ep.tissue,
                "ctrl_fpkm":    ep.ctrl_fpkm,
                "stress_fpkm":  ep.stress_fpkm,
                "log2fc":       ep.log2fc,
                "regulation":   ep.regulation,
            }
            for ep in packet.expression
        ],
        "stress_summary": [
            {
                "stress":     s.stress,
                "avg_log2fc": s.avg_log2fc,
                "n_up":       s.n_up,
                "n_down":     s.n_down,
                "n_total":    s.n_total,
                "consensus":  s.consensus,
                "confidence": s.confidence,
            }
            for s in packet.stress_summary
        ],
        "peptide":            packet.peptide,
        "biochem_properties": packet.biochem_properties,
        "nan_pairs_skipped": packet.nan_pairs,
        "files_checked":     packet.files_checked,
        "files_with_gene":   packet.files_with_gene,
        "errors":            packet.errors,
    }
