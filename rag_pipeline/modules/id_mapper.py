"""
id_mapper.py  (v2 — correct CSV-based lookup)
---------------------------------------------
Bidirectional gene ID mapper for the Chickpea Stress-Gene RAG pipeline.

PREVIOUS BUG:
  The old implementation ran a regex to extract digits and zero-padded them,
  turning LOC101488545 → Ca_101488545 (completely wrong — 8-digit number kept).
  It never actually looked at mapping.csv for LOC IDs.

CORRECT BEHAVIOUR:
  mapping.csv has two columns:
    "Transcript id"  →  Ca_XXXXX  (5-digit canonical form)
    "LOC id"         →  LOC1XXXXXXX  |  gene symbol  |  other alias

  Lookup direction:
    Ca_XXXXX input  → accepted directly (normalised)
    LOC/symbol input → look it up in the "LOC id" column, return the
                       corresponding "Transcript id" (Ca_XXXXX)

  If not found → return input as-is, with a warning flag (so downstream
  CSV lookups will naturally miss and report "no data" rather than crashing).

Supported input formats:
  Ca_00003          canonical Ca ID
  LOC101488545      NCBI LOC ID      → Ca_00003
  ARF1, NAC01       gene symbols     → Ca_00010, Ca_00111
  Any other string  → passed through unchanged with a note
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

# ── Default mapping path ───────────────────────────────────────────────────────
_DEFAULT_MAPPING = Path(__file__).resolve().parents[2] / "mapping.csv"

# ── Ca_XXXXX pattern ───────────────────────────────────────────────────────────
_CA_RE = re.compile(r"^Ca[_\s]?\d{5}$", re.IGNORECASE)


def _canonical_ca_id(raw: str) -> str:
    """Normalise any Ca_XXXXX variant to clean Ca_XXXXX (5-digit, underscore)."""
    digits = re.sub(r"[^0-9]", "", raw).zfill(5)
    return f"Ca_{digits}"


def _clean(value: str) -> str:
    return value.strip()


# ── Load mapping tables (cached once per process) ─────────────────────────────
@lru_cache(maxsize=1)
def _load_mapping_tables(mapping_csv: str) -> tuple[dict[str, str], dict[str, str]]:
    """
    Build lookup tables from mapping.csv.

    Returns
    -------
    (loc_to_ca, ca_to_loc)
        loc_to_ca : {UPPERCASE LOC/alias → canonical Ca_XXXXX}
        ca_to_loc : {UPPERCASE Ca_ID     → original LOC/alias string}

    One-to-one: each LOC maps to exactly one Ca ID per the CSV.
    If duplicates exist, last row wins (consistent with pandas behaviour).
    """
    loc_to_ca: dict[str, str] = {}
    ca_to_loc: dict[str, str] = {}

    path = Path(mapping_csv)
    if not path.exists():
        return loc_to_ca, ca_to_loc

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ca_raw  = _clean(row.get("Transcript id", ""))
            loc_raw = _clean(row.get("LOC id", ""))

            if not ca_raw:
                continue

            ca_norm  = _canonical_ca_id(ca_raw)
            loc_norm = loc_raw.upper()

            ca_to_loc[ca_norm.upper()] = loc_raw     # Ca → LOC
            if loc_norm:
                loc_to_ca[loc_norm] = ca_norm         # LOC → Ca

    return loc_to_ca, ca_to_loc


# ── Public API ─────────────────────────────────────────────────────────────────
def resolve_to_ca(
    gene_id: str,
    mapping_path: str = str(_DEFAULT_MAPPING),
) -> dict:
    """
    Resolve any gene identifier to its canonical Ca_XXXXX form.

    Parameters
    ----------
    gene_id      : Any identifier (Ca_XXXXX, LOC…, ARF1, etc.)
    mapping_path : Path to mapping.csv

    Returns
    -------
    dict:
        input_id    : str   original input (unchanged)
        ca_id       : str   resolved canonical Ca_XXXXX (or input if not found)
        external_id : str   the LOC/alias for this Ca ID (from mapping)
        resolved    : bool  True if a valid mapping was found
        was_ca      : bool  True if input was already in Ca_XXXXX format
        note        : str   human-readable explanation
    """
    raw   = gene_id.strip()
    upper = raw.upper()

    loc_to_ca, ca_to_loc = _load_mapping_tables(mapping_path)

    # ── Case 1: Already a Ca_XXXXX ────────────────────────────────────────────
    if _CA_RE.match(upper):
        ca_norm  = _canonical_ca_id(raw)
        ext_id   = ca_to_loc.get(ca_norm.upper(), "")
        return {
            "input_id":    raw,
            "ca_id":       ca_norm,
            "external_id": ext_id,
            "resolved":    True,
            "was_ca":      True,
            "note":        f"[ID_MAPPER] '{raw}' is already a canonical Ca ID → {ca_norm}",
        }

    # ── Case 2: LOC / symbol lookup in mapping.csv ────────────────────────────
    ca_found = loc_to_ca.get(upper)

    if ca_found:
        return {
            "input_id":    raw,
            "ca_id":       ca_found,
            "external_id": raw,
            "resolved":    True,
            "was_ca":      False,
            "note":        f"[ID_MAPPER] '{raw}' → mapped to {ca_found} via mapping.csv",
        }

    # ── Case 3: Not found ─────────────────────────────────────────────────────
    return {
        "input_id":    raw,
        "ca_id":       raw,          # pass through unchanged
        "external_id": "",
        "resolved":    False,
        "was_ca":      False,
        "note":        (
            f"[ID_MAPPER] '{raw}' not found in mapping.csv (checked {len(loc_to_ca)} LOC entries). "
            "Passed through unchanged — downstream data lookups may not find a match."
        ),
    }


def resolve_many(
    gene_ids: list[str],
    mapping_path: str = str(_DEFAULT_MAPPING),
) -> list[dict]:
    """Resolve a list of gene identifiers. Returns list of result dicts."""
    return [resolve_to_ca(gid, mapping_path) for gid in gene_ids]


def ca_to_external(
    ca_id: str,
    mapping_path: str = str(_DEFAULT_MAPPING),
) -> Optional[str]:
    """Return the LOC/alias for a canonical Ca_XXXXX, or None if not in mapping."""
    _, ca_to_loc = _load_mapping_tables(mapping_path)
    return ca_to_loc.get(ca_id.strip().upper())
