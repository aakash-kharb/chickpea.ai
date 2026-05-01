"""
gene_search_agent.py
--------------------
Agent for list-based gene queries where no specific Ca_XXXXX ID is provided.

Example queries handled:
  - "give me 3 cold resistant genes"
  - "which genes are upregulated under heat stress?"
  - "list top drought-responsive genes"
  - "find genes responsive to multiple stresses"

Data sources:
  - Stress_Binary_Matrix.csv  → for stress label filtering
  - Individual expression files → for regulation filtering (optional, slower)

Returns the top N matching gene IDs with their stress labels and summary
expression data, ready to be injected into the LLM prompt.
"""

import os
import math
import pandas as pd
from functools import lru_cache
from typing import Optional

# ── Defaults ───────────────────────────────────────────────────────────────────
_STRESS_COLS = ["Cold", "Drought", "Salinity", "Heat"]

_DEFAULT_STRESS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "Stress_Binary_Matrix.csv"
)
_DEFAULT_INDIV_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "Individual Files"
)


# ── Data loading ───────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_stress_matrix(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df["Ca_ID"] = df["Ca_ID"].str.strip().str.upper()
    for col in _STRESS_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "Num_Stresses" in df.columns:
        df["Num_Stresses"] = pd.to_numeric(
            df["Num_Stresses"], errors="coerce"
        ).fillna(0).astype(int)
    return df.set_index("Ca_ID")


# ── Public API ─────────────────────────────────────────────────────────────────
def search_genes(
    stress_filter: Optional[str] = None,
    regulation_filter: Optional[str] = None,
    n_genes: int = 5,
    stress_matrix_path: str = _DEFAULT_STRESS_PATH,
    indiv_dir: str = _DEFAULT_INDIV_DIR,
) -> dict:
    """
    Search for genes matching stress/regulation criteria.

    Parameters
    ----------
    stress_filter : str, optional
        One of "Cold", "Drought", "Salinity", "Heat".
        If None, returns genes responsive to any stress.
    regulation_filter : str, optional
        "UPREGULATED" or "DOWNREGULATED".
        If None, returns all stress-responsive genes.
    n_genes : int
        Maximum number of genes to return.
    stress_matrix_path, indiv_dir : str
        Override data paths (useful for testing).

    Returns
    -------
    dict with keys:
        found          : bool
        query_params   : dict  (what was searched)
        genes          : list of {gene_id, stress_labels, active_stresses, num_stresses}
        total_matched  : int
        retrieval_note : str
    """
    # ── Step 1: Filter by stress binary labels ─────────────────────────────────
    df = _load_stress_matrix(str(stress_matrix_path))
    candidate_df = df.copy()

    if stress_filter and stress_filter in _STRESS_COLS:
        stress_col = stress_filter.capitalize()
        if stress_col in candidate_df.columns:
            candidate_df = candidate_df[candidate_df[stress_col] == 1]

    # Sort by Num_Stresses descending (multi-stress genes are more interesting)
    if "Num_Stresses" in candidate_df.columns:
        candidate_df = candidate_df.sort_values("Num_Stresses", ascending=False)

    total_candidates = len(candidate_df)

    if total_candidates == 0:
        return {
            "found": False,
            "query_params": {
                "stress_filter": stress_filter,
                "regulation_filter": regulation_filter,
                "n_genes": n_genes,
            },
            "genes": [],
            "total_matched": 0,
            "retrieval_note": (
                f"[GENE_SEARCH] No genes found with stress_filter='{stress_filter}'."
            ),
        }

    # ── Step 2: Optional regulation filter (expression-level) ─────────────────
    # Only apply if expression data directory exists and regulation is specified
    if regulation_filter and os.path.isdir(indiv_dir):
        filtered_ids = _filter_by_regulation(
            list(candidate_df.index),
            stress_filter=stress_filter,
            regulation_filter=regulation_filter,
            indiv_dir=indiv_dir,
            limit=n_genes * 3,      # oversample, then trim
        )
        # Fall back to all candidates if regulation filter yields nothing
        if filtered_ids:
            candidate_df = candidate_df.loc[
                [g for g in filtered_ids if g in candidate_df.index]
            ]

    # ── Step 3: Build result list (randomized within priority tiers) ────────────
    # Group by Num_Stresses so multi-stress genes are prioritized,
    # but within each tier, randomly sample for variety.
    import random
    remaining_slots = n_genes
    selected_rows = []

    if "Num_Stresses" in candidate_df.columns:
        for _, tier_df in candidate_df.groupby("Num_Stresses", sort=False):
            if remaining_slots <= 0:
                break
            tier_list = list(tier_df.iterrows())
            sample_size = min(remaining_slots, len(tier_list))
            selected_rows.extend(random.sample(tier_list, sample_size))
            remaining_slots -= sample_size
    else:
        # Fallback: random sample from entire candidate set
        all_rows = list(candidate_df.iterrows())
        sample_size = min(n_genes, len(all_rows))
        selected_rows = random.sample(all_rows, sample_size)

    genes_out = []
    for gene_id, row in selected_rows:
        stress_labels = {
            col: int(row[col]) for col in _STRESS_COLS if col in candidate_df.columns
        }
        active = [s for s, v in stress_labels.items() if v == 1]
        num = int(row.get("Num_Stresses", len(active)))
        stress_str = str(row.get("Stress", "")).strip() if "Stress" in row else ""

        genes_out.append({
            "gene_id":        gene_id,
            "stress_labels":  stress_labels,
            "active_stresses": active,
            "num_stresses":   num,
            "stress_string":  stress_str,
        })

    note = (
        f"[GENE_SEARCH] Found {total_candidates} gene(s) matching "
        f"stress='{stress_filter or 'any'}', "
        f"regulation='{regulation_filter or 'any'}'. "
        f"Returning top {len(genes_out)}."
    )

    return {
        "found": len(genes_out) > 0,
        "query_params": {
            "stress_filter": stress_filter,
            "regulation_filter": regulation_filter,
            "n_genes": n_genes,
        },
        "genes": genes_out,
        "total_matched": total_candidates,
        "retrieval_note": note,
    }


def format_gene_search_context(
    stress_filter: Optional[str] = None,
    regulation_filter: Optional[str] = None,
    n_genes: int = 5,
    stress_matrix_path: str = _DEFAULT_STRESS_PATH,
    indiv_dir: str = _DEFAULT_INDIV_DIR,
) -> str:
    """Return a plain-text context block for injection into an LLM prompt."""
    result = search_genes(
        stress_filter=stress_filter,
        regulation_filter=regulation_filter,
        n_genes=n_genes,
        stress_matrix_path=stress_matrix_path,
        indiv_dir=indiv_dir,
    )

    header = (
        f"=== Gene Search Results "
        f"[stress={stress_filter or 'any'}, "
        f"regulation={regulation_filter or 'any'}, "
        f"top {n_genes}] ===\n"
        f"{result['retrieval_note']}\n"
    )

    if not result["found"]:
        return header

    lines = [header]
    lines.append(
        f"{'Gene ID':<14} {'Num Stresses':>13} {'Active Stresses'}"
    )
    lines.append("─" * 55)
    for g in result["genes"]:
        active_str = ", ".join(g["active_stresses"]) or "none"
        lines.append(
            f"{g['gene_id']:<14} "
            f"{g['num_stresses']:>13}  "
            f"{active_str}"
        )

    return "\n".join(lines) + "\n"


# ── Expression-level regulation filter (internal) ─────────────────────────────
def _filter_by_regulation(
    gene_ids: list,
    stress_filter: Optional[str],
    regulation_filter: str,
    indiv_dir: str,
    limit: int = 30,
) -> list:
    """
    Filter gene_ids to those showing the requested regulation under stress_filter.
    Returns list of gene IDs (UPPERCASE) sorted by avg |log2FC| descending.
    """
    try:
        from modules.expression_agent import get_expression_data, LOG2FC_UP, LOG2FC_DOWN
    except ImportError:
        return []

    scored = []
    for gid in gene_ids[:limit]:
        try:
            data = get_expression_data(gid, indiv_dir)
        except Exception:
            continue

        if not data["found"]:
            continue

        summary = data["stress_summary"]
        target_st = (stress_filter or "").upper()

        for st, s in summary.items():
            if target_st and st != target_st:
                continue
            consensus = s.get("consensus_regulation", "")
            if regulation_filter == "UPREGULATED" and consensus == "UPREGULATED":
                scored.append((gid, s["avg_log2fc"]))
            elif regulation_filter == "DOWNREGULATED" and consensus == "DOWNREGULATED":
                scored.append((gid, s["avg_log2fc"]))

    scored.sort(key=lambda x: abs(x[1]), reverse=True)
    return [g for g, _ in scored]
