"""
semantic_router.py
------------------
Lightweight intent classifier for incoming user queries.

No external model is used — pure keyword/pattern matching.
This keeps the router fast, deterministic, and offline-capable.

Intent categories
-----------------
  GENE_PROFILE   → "tell me about Ca_00011", "what is Ca_00001?"
  EXPRESSION     → "expression", "upregulated", "log2fc", "FPKM"
  SEQUENCE       → "sequence", "peptide", "amino acid", "protein"
  STRESS_LABEL   → "stress", "responsive", "classified", "drought"
  COMPARISON     → "compare", "vs", "difference between"
  GENERAL        → anything else → triggers full pipeline

Router outputs a list of recommended agents to invoke for the query.
"""

import re

# ── Keyword maps ───────────────────────────────────────────────────────────────
_INTENT_PATTERNS = {
    "EXPRESSION": [
        r"\bexpression\b", r"\bfpkm\b", r"\bupregulat\b", r"\bdownregulat\b",
        r"\blog2fc\b", r"\bfold.change\b", r"\brna.seq\b", r"\btranscript\b",
        r"\bdifferentially\b", r"\bDE\b",
    ],
    "SEQUENCE": [
        r"\bsequence\b", r"\bpeptide\b", r"\bamino.acid\b", r"\bprotein\b",
        r"\bproline\b", r"\bcysteine\b", r"\bhydrophobic\b", r"\bcharged\b",
        r"\bAA composition\b", r"\bCKSAAP\b",
    ],
    "STRESS_LABEL": [
        r"\bstress\b", r"\breadonly\b", r"\bresponsive\b", r"\bclassif\b",
        r"\bdrought\b", r"\bsalin\b", r"\bcold\b", r"\bheat\b",
        r"\bstress.label\b", r"\bbinary\b",
    ],
    "COMPARISON": [
        r"\bcompare\b", r"\bvs\.?\b", r"\bversus\b", r"\bdifference\b",
        r"\bcontrast\b",
    ],
}

# If these are detected → also activate expression agent
_EXPRESSION_TRIGGERS = _INTENT_PATTERNS["EXPRESSION"]

# Gene ID regex
_GENE_ID_RE = re.compile(r"\bCa[_\s]?\d{5}\b", re.IGNORECASE)


# ── Public API ─────────────────────────────────────────────────────────────────
def route_query(query: str) -> dict:
    """
    Classify a natural-language query and determine which agents to activate.

    Parameters
    ----------
    query : str
        The raw user query.

    Returns
    -------
    dict:
        intent          : str   primary intent label
        agents          : list  agents to invoke  (e.g. ["expression", "sequence"])
        gene_ids        : list  Ca_XXXXX IDs detected in query (may be empty)
        router_note     : str   human-readable explanation
    """
    q_lower = query.lower()

    # ── Detect gene IDs ────────────────────────────────────────────────────────
    raw_matches = _GENE_ID_RE.findall(query)
    gene_ids = [
        "CA_" + re.sub(r"[^0-9]", "", m).zfill(5)
        for m in raw_matches
    ]
    # Reformat to canonical Ca_XXXXX
    gene_ids = [
        "Ca_" + g.split("_")[1] if "_" in g else g
        for g in gene_ids
    ]

    # ── Score each intent ──────────────────────────────────────────────────────
    scores = {}
    for intent, patterns in _INTENT_PATTERNS.items():
        scores[intent] = sum(
            1 for p in patterns if re.search(p, query, re.IGNORECASE)
        )

    # Determine primary intent
    best_intent = max(scores, key=scores.get)
    best_score  = scores[best_intent]

    # ── Select agents ──────────────────────────────────────────────────────────
    if best_score == 0:
        # No specific intent → run full pipeline
        primary_intent = "GENE_PROFILE"
        agents = ["expression", "sequence", "stress_label"]
        note = "No specific intent detected → running full gene profile pipeline."
    elif best_intent == "COMPARISON":
        primary_intent = "COMPARISON"
        agents = ["expression", "stress_label"]
        note = "Comparison query → activating expression + stress label agents."
    else:
        primary_intent = best_intent
        agents = []
        # Always activate any intent that scored ≥ 1
        if scores["EXPRESSION"] >= 1:
            agents.append("expression")
        if scores["SEQUENCE"] >= 1:
            agents.append("sequence")
        if scores["STRESS_LABEL"] >= 1:
            agents.append("stress_label")
        # If still empty (shouldn't happen here), default to all
        if not agents:
            agents = ["expression", "sequence", "stress_label"]
        note = (
            f"Intent={primary_intent} | "
            f"Scores: {scores} → agents: {agents}"
        )

    # If gene IDs detected and GENE_PROFILE suspected → activate full pipeline
    if gene_ids and not agents:
        agents = ["expression", "sequence", "stress_label"]
        primary_intent = "GENE_PROFILE"

    return {
        "intent": primary_intent,
        "agents": list(dict.fromkeys(agents)),   # deduplicate, preserve order
        "gene_ids": gene_ids,
        "router_note": f"[SEMANTIC_ROUTER] {note}",
    }
