"""
biochem_properties.py — Biochemical property lookup for chickpea peptides
--------------------------------------------------------------------------
Reads pre-computed properties from BiochemicalProperties.csv and returns
them as structured dicts for LLM context injection.

CSV columns:
  Transcript id, Peptide, Total Amino Acids, Molecular Weight (Da),
  Theoretical pI, Instability Index, Aliphatic Index, GRAVY, Status,
  Total C Atoms, Total H Atoms, Total N Atoms, Total O Atoms, Total S Atoms
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_MODULE_DIR   = Path(__file__).resolve().parent
_PROJECT_ROOT = _MODULE_DIR.parents[1]
_DEFAULT_CSV  = _PROJECT_ROOT / "BiochemicalProperties.csv"


@dataclass
class BiochemProperties:
    """All biochemical properties for one peptide."""
    transcript_id:      str
    total_amino_acids:  int
    molecular_weight:   float    # Da
    theoretical_pi:     float
    instability_index:  float
    aliphatic_index:    float
    gravy:              float
    status:             str      # "Success" or error indicator
    total_c_atoms:      int
    total_h_atoms:      int
    total_n_atoms:      int
    total_o_atoms:      int
    total_s_atoms:      int


@lru_cache(maxsize=1)
def _load_biochem_csv(csv_path: str) -> dict[str, dict[str, str]]:
    """
    Load BiochemicalProperties.csv into a dict keyed by UPPERCASE transcript id.
    Cached so repeated lookups don't re-read the file.
    """
    result: dict[str, dict[str, str]] = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            tid = (row.get("Transcript id") or "").strip().upper()
            if tid:
                result[tid] = row
    return result


def lookup_biochem_properties(
    gene_id: str,
    csv_path: Path = _DEFAULT_CSV,
) -> Optional[BiochemProperties]:
    """
    Look up pre-computed biochemical properties for a gene ID.

    Parameters
    ----------
    gene_id  : str   Ca_XXXXX identifier (case-insensitive)
    csv_path : Path  Path to BiochemicalProperties.csv

    Returns
    -------
    BiochemProperties if found, None otherwise.
    """
    if not csv_path.exists():
        return None

    data = _load_biochem_csv(str(csv_path))
    norm_id = gene_id.strip().upper()
    row = data.get(norm_id)

    if row is None:
        return None

    try:
        return BiochemProperties(
            transcript_id     = row.get("Transcript id", "").strip(),
            total_amino_acids = int(row.get("Total Amino Acids", 0)),
            molecular_weight  = float(row.get("Molecular Weight (Da)", 0)),
            theoretical_pi    = float(row.get("Theoretical pI", 0)),
            instability_index = float(row.get("Instability Index", 0)),
            aliphatic_index   = float(row.get("Aliphatic Index", 0)),
            gravy             = float(row.get("GRAVY", 0)),
            status            = row.get("Status", "Unknown").strip(),
            total_c_atoms     = int(row.get("Total C Atoms", 0)),
            total_h_atoms     = int(row.get("Total H Atoms", 0)),
            total_n_atoms     = int(row.get("Total N Atoms", 0)),
            total_o_atoms     = int(row.get("Total O Atoms", 0)),
            total_s_atoms     = int(row.get("Total S Atoms", 0)),
        )
    except (ValueError, TypeError):
        return None


def biochem_to_dict(props: BiochemProperties) -> dict:
    """Convert BiochemProperties to a plain dict for JSON / LLM injection."""
    return {
        "transcript_id":      props.transcript_id,
        "total_amino_acids":  props.total_amino_acids,
        "molecular_weight":   props.molecular_weight,
        "theoretical_pi":     props.theoretical_pi,
        "instability_index":  props.instability_index,
        "aliphatic_index":    props.aliphatic_index,
        "gravy":              props.gravy,
        "status":             props.status,
        "total_c_atoms":      props.total_c_atoms,
        "total_h_atoms":      props.total_h_atoms,
        "total_n_atoms":      props.total_n_atoms,
        "total_o_atoms":      props.total_o_atoms,
        "total_s_atoms":      props.total_s_atoms,
    }


def format_biochem_context(props: BiochemProperties) -> str:
    """
    Format biochemical properties as a compact text block for LLM context.
    """
    stability = "Stable" if props.instability_index < 40 else "Unstable"
    lines = [
        f"Biochemical Properties ({props.transcript_id}):",
        f"  Total Amino Acids : {props.total_amino_acids}",
        f"  Molecular Weight  : {props.molecular_weight:,.2f} Da",
        f"  Theoretical pI    : {props.theoretical_pi:.2f}",
        f"  Instability Index : {props.instability_index:.2f}  ({stability})",
        f"  Aliphatic Index   : {props.aliphatic_index:.2f}",
        f"  GRAVY             : {props.gravy:.4f}",
        f"  Atomic Composition:",
        f"    C={props.total_c_atoms}  H={props.total_h_atoms}  "
        f"N={props.total_n_atoms}  O={props.total_o_atoms}  S={props.total_s_atoms}",
    ]
    return "\n".join(lines)


def format_biochem_markdown(props: BiochemProperties) -> str:
    """
    Format biochemical properties as a Markdown table for human-readable output.
    """
    stability = "Stable" if props.instability_index < 40 else "Unstable"
    lines = [
        "### Biochemical Properties",
        "",
        "| Property | Value |",
        "| --- | ---: |",
        f"| Total Amino Acids | {props.total_amino_acids} |",
        f"| Molecular Weight | {props.molecular_weight:,.2f} Da |",
        f"| Theoretical pI | {props.theoretical_pi:.2f} |",
        f"| Instability Index | {props.instability_index:.2f} ({stability}) |",
        f"| Aliphatic Index | {props.aliphatic_index:.2f} |",
        f"| GRAVY | {props.gravy:.4f} |",
        "",
        "### Atomic Composition",
        "",
        "| Atom | Count |",
        "| :---: | ---: |",
        f"| C | {props.total_c_atoms} |",
        f"| H | {props.total_h_atoms} |",
        f"| N | {props.total_n_atoms} |",
        f"| O | {props.total_o_atoms} |",
        f"| S | {props.total_s_atoms} |",
    ]
    return "\n".join(lines)
