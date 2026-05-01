"""
ai_router.py  (v2 — scope-aware, metadata-rich routing)
--------------------------------------------------------
AI-powered intent classifier for the Chickpea Stress-Gene RAG pipeline.

WHAT'S NEW IN v2
────────────────
① Scope gate       — OUT_OF_SCOPE intent for unrelated queries (maths, coding,
                     general science outside chickpea transcriptomics, etc.)
② Multi-ID support — all Ca_XXXXX / LOC / symbol IDs extracted; pipeline
                     collects packets for every ID and validator checks coverage.
③ Routing capsule  — router attaches explicit instructions for the validator
                     (required_sections, token_budget, expected_gene_ids) so
                     AI-2 and AI-3 agree on what a correct answer looks like.
④ Token budget     — router hints how long the answer should be so AI-2 does
                     not waste tokens on phantom sections with "No data".

Output contract
───────────────
{
  "intent"            : str   GENE_PROFILE | GENE_LIST | EXPRESSION |
                              SEQUENCE | STRESS_LABEL | COMPARISON | OUT_OF_SCOPE
  "gene_ids"          : list  all Ca_XXXXX ids in query (may be LOC/symbol, resolved later)
  "agents"            : list  ["expression", "sequence", "stress_label", "gene_search"]
  "stress_filter"     : str|None
  "regulation_filter" : str|None
  "n_genes_requested" : int|None
  "output_format"     : str   "FULL_PROFILE" | "COMPACT_LIST" | "FOCUSED" | "NONE"
  "required_sections" : list  sections the validator will enforce
  "token_budget"      : str   "LONG" | "MEDIUM" | "SHORT"
  "router_note"       : str
}
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

# ── Gene ID regex (canonical Ca_XXXXX + LOC + common gene symbols) ─────────────
_GENE_ID_RE = re.compile(r"\b(Ca[_\s]?\d{5}|LOC\d{6,})\b", re.IGNORECASE)

# ── Keywords that suggest the query is IN scope even without a gene ID ──────────
_IN_SCOPE_HINTS = re.compile(
    r"\b(gene|protein|stress|drought|salinity|cold|heat|chickpea|cicer|fpkm|"
    r"expression|rna.?seq|log2fc|upregulat|downregulat|transcriptom|sequence|"
    r"peptide|amino acid|cultivar|responsive|regulation|biological)\b",
    re.IGNORECASE,
)

# ── Router system prompt ───────────────────────────────────────────────────────
_ROUTER_SYSTEM = """\
You are the routing agent for a Chickpea (Cicer arietinum) stress-gene RAG pipeline.
Your ONLY job is to classify the user query and return a JSON routing decision.

═══ SCOPE GATE — THE MOST IMPORTANT RULE ═══════════════════════════════════════
First decide: is this query IN SCOPE for a chickpea genomics pipeline?
IN SCOPE examples:
  • Questions about specific genes (Ca_XXXXX, LOC IDs, gene symbols)
  • Stress response, expression data, fold-change, RNA-seq, FPKM
  • Peptide/protein sequences, amino acid composition
  • Breeding, cultivar comparison, transcriptomics
  • Any query mixing biology with the above topics

OUT OF SCOPE — set intent="OUT_OF_SCOPE" for:
  • Pure mathematics   ("5 × 59?", "integrate x²dx")
  • General coding     ("write a Python script", "fix my SQL")
  • Non-plant science  ("explain gravity", "human cancer genes")
  • General knowledge  ("capital of France", "who is Einstein")
  • Requests for help unrelated to chickpea genomics

If IN SCOPE → continue with the full routing below.
═════════════════════════════════════════════════════════════════════════════════

═══ INTENT LABELS ═══════════════════════════════════════════════════════════════
GENE_PROFILE  → analyse one or more specific genes comprehensively
EXPRESSION    → expression / fold-change / FPKM focused question
SEQUENCE      → peptide sequence / amino acid composition focused
STRESS_LABEL  → stress binary classification focused
GENE_LIST     → user wants a list of genes matching criteria (no specific ID)
COMPARISON    → comparing two or more genes or conditions

═══ AGENTS ══════════════════════════════════════════════════════════════════════
"expression"   → FPKM, Log2FC, regulation per tissue/cultivar
"sequence"     → peptide sequence, amino acid composition
"stress_label" → Cold/Drought/Salinity/Heat binary labels
"gene_search"  → for GENE_LIST queries (search by stress/regulation criteria)

═══ OUTPUT FORMAT GUIDANCE ══════════════════════════════════════════════════════
Set output_format and required_sections to tell AI-2 what to produce:

Intent         | output_format   | required_sections                       | token_budget
───────────────┼─────────────────┼─────────────────────────────────────────┼─────────────
GENE_PROFILE   | FULL_PROFILE    | Summary, Expression Evidence, Stress    | LONG
(1-3 genes)    |                 | Classification, Sequence Analysis,      |
               |                 | Confidence Assessment, Biological       |
               |                 | Insights                                |
GENE_LIST      | COMPACT_LIST    | Summary, Stress Classification,         | MEDIUM
               |                 | Biological Insights                     |
EXPRESSION     | FOCUSED         | Summary, Expression Evidence,           | MEDIUM
               |                 | Confidence Assessment                   |
SEQUENCE       | FOCUSED         | Summary, Sequence Analysis,             | SHORT-MEDIUM
               |                 | Biological Insights                     |
STRESS_LABEL   | FOCUSED         | Summary, Stress Classification          | SHORT
COMPARISON     | FULL_PROFILE    | All sections, one subsection per gene   | LONG
OUT_OF_SCOPE   | NONE            | []                                      | SHORT

═══ MULTI-ID RULES ══════════════════════════════════════════════════════════════
If multiple gene IDs are present:
  • List ALL of them in gene_ids.
  • Use intent=GENE_PROFILE if ≤3 IDs; COMPARISON if user asks to compare.
  • Validator will check that every ID in gene_ids is covered in the response.

═══ EXAMPLES ════════════════════════════════════════════════════════════════════
Query: "Is Ca_00999 upregulated under heat?"
→ intent=EXPRESSION, gene_ids=["Ca_00999"], output_format=FOCUSED,
  required_sections=["Summary","Expression Evidence","Confidence Assessment"]

Query: "Give me 5 drought-responsive genes"
→ intent=GENE_LIST, output_format=COMPACT_LIST,
  required_sections=["Summary","Stress Classification","Biological Insights"]

Query: "What is 5 times 59?"
→ intent=OUT_OF_SCOPE, output_format=NONE, required_sections=[]

Query: "Compare Ca_00001 and Ca_00999 under salinity"
→ intent=COMPARISON, gene_ids=["Ca_00001","Ca_00999"], output_format=FULL_PROFILE

Respond with ONLY valid JSON — no markdown, no text outside the JSON block:
{
  "intent": "GENE_PROFILE",
  "gene_ids": ["Ca_00011"],
  "agents": ["expression", "sequence", "stress_label"],
  "stress_filter": null,
  "regulation_filter": null,
  "n_genes_requested": null,
  "output_format": "FULL_PROFILE",
  "required_sections": ["Summary", "Expression Evidence", "Stress Classification",
                        "Sequence Analysis", "Confidence Assessment", "Biological Insights"],
  "token_budget": "LONG",
  "router_note": "Single gene comprehensive profile"
}
"""


# ── Out-of-scope canned response ───────────────────────────────────────────────
_OUT_OF_SCOPE_RESPONSE = """\
This pipeline is designed exclusively for **chickpea (Cicer arietinum) stress-gene analysis** — \
including RNA-seq expression data, stress binary classification, peptide sequences, and related \
transcriptomics queries.

Your question appears to be outside this scope. Please ask about:
- Specific genes: e.g. *"Is Ca_00999 upregulated under drought?"*
- Gene lists: e.g. *"Give me 5 heat-responsive genes"*
- Expression: e.g. *"What is the Log2FC for Ca_00011 under salinity?"*
- Sequences: e.g. *"Show me the peptide sequence and amino acid composition of Ca_00001"*
"""


# ── Public API ─────────────────────────────────────────────────────────────────
def route_query_ai(query: str, conversation_history: list = None) -> dict:
    """
    AI-powered query router with fallback to pattern-based router.

    Returns a routing dict including the 'routing_capsule' that the validator
    uses to check completeness and format of AI-2's response.

    Parameters
    ----------
    query : str
        The raw user query.
    conversation_history : list, optional
        List of ConversationTurn objects from previous queries.
        Used to detect follow-up questions and inherit gene IDs.
    """
    from modules.llm_interface import get_llm_response_with_model, get_router_model_name

    try:
        router_model = get_router_model_name()

        # ── Inject conversation context for follow-up detection ────────────────
        system_prompt = _ROUTER_SYSTEM
        if conversation_history:
            prev = conversation_history[-1]
            prev_gene_str = ', '.join(prev.gene_ids) if prev.gene_ids else 'none'
            conv_block = (
                f"\n=== CONVERSATION CONTEXT ===\n"
                f"Previous query: \"{prev.query}\"\n"
                f"Previous gene IDs: {prev_gene_str}\n"
                f"Previous intent: {prev.intent}\n"
                f"===\n"
                f"If the current query seems like a follow-up to the above "
                f"(e.g. \"what about its sequence?\", \"is it drought responsive?\", "
                f"\"tell me more\"), and the current query does NOT contain an explicit "
                f"gene ID, inherit the gene_ids from the previous turn.\n"
                f"If the current query contains a NEW explicit gene ID, treat it as "
                f"a fresh query — do NOT inherit previous gene IDs.\n"
            )
            system_prompt = system_prompt + conv_block

        raw = get_llm_response_with_model(
            system_prompt,
            f"Route this query: {query}",
            model=router_model,
        )

        # Strip markdown code fences if model added them
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"```(?:json)?", "", clean).strip().strip("`").strip()

        data = json.loads(clean)

        # ── Normalise gene IDs ─────────────────────────────────────────────────
        raw_ids = data.get("gene_ids", [])
        gene_ids = _normalise_gene_ids(raw_ids)
        # Scan original query too — catch any the LLM missed
        for m in _GENE_ID_RE.finditer(query):
            gid = m.group()
            norm = _format_gene_id(gid)
            if norm not in gene_ids:
                gene_ids.append(norm)

        agents = list(dict.fromkeys(data.get("agents", ["expression", "sequence", "stress_label"])))
        intent = data.get("intent", "GENE_PROFILE")

        # ── Scope gate: fast-path OUT_OF_SCOPE ────────────────────────────────
        if intent == "OUT_OF_SCOPE":
            return _out_of_scope_result(query, note=f"[AI_ROUTER] {data.get('router_note', '')}")

        # ── Build routing capsule (passed verbatim to validator) ───────────────
        required_sections = data.get("required_sections", [])
        token_budget      = data.get("token_budget", "LONG")
        output_format     = data.get("output_format", "FULL_PROFILE")

        routing_capsule = _build_routing_capsule(
            intent           = intent,
            gene_ids         = gene_ids,
            required_sections= required_sections,
            token_budget     = token_budget,
            output_format    = output_format,
            query            = query,
        )

        return {
            "intent":             intent,
            "gene_ids":           gene_ids,
            "agents":             agents,
            "stress_filter":      data.get("stress_filter"),
            "regulation_filter":  data.get("regulation_filter"),
            "n_genes_requested":  data.get("n_genes_requested"),
            "output_format":      output_format,
            "required_sections":  required_sections,
            "token_budget":       token_budget,
            "routing_capsule":    routing_capsule,
            "router_note":        f"[AI_ROUTER] {data.get('router_note', '')}",
        }

    except Exception as exc:
        return _fallback_route(query, reason=str(exc))


# ── Routing capsule builder ────────────────────────────────────────────────────
def _build_routing_capsule(
    intent: str,
    gene_ids: list,
    required_sections: list,
    token_budget: str,
    output_format: str,
    query: str,
) -> str:
    """
    Build a plain-text capsule passed from AI-1 (router) to AI-3 (validator).
    The validator reads this to know exactly what AI-2 was supposed to produce.
    """
    lines = [
        "=== ROUTING CAPSULE (from AI-1 Router to AI-3 Validator) ===",
        f"Original query   : {query}",
        f"Intent           : {intent}",
        f"Output format    : {output_format}",
        f"Token budget     : {token_budget}",
    ]
    if gene_ids:
        lines.append(f"Expected gene IDs: {', '.join(gene_ids)}")
        lines.append("  → Validator MUST check: every gene ID above is addressed in the response.")
    else:
        lines.append("Expected gene IDs: none (gene list query — IDs chosen by gene_search_agent)")

    if required_sections:
        lines.append(f"Required sections: {', '.join(required_sections)}")
        lines.append("  → Validator MUST check: all required sections are present and non-trivial.")
    else:
        lines.append("Required sections: none (out-of-scope or minimal response)")

    budget_rules = {
        "SHORT":  "Response should be concise (≤200 words). No phantom sections.",
        "MEDIUM": "Response should be focused (200-500 words). Only required sections.",
        "LONG":   "Response can be comprehensive (500+ words). All required sections.",
    }
    lines.append(f"Length rule      : {budget_rules.get(token_budget, '')}")
    lines.append("")
    lines.append("VALIDATOR RULES:")
    lines.append("  1. Do NOT add sections that are not in Required sections list.")
    lines.append("  2. Do NOT include sections that say 'No data available' — omit them.")
    lines.append("  3. If gene IDs are listed above, verify each gets at least one data point or")
    lines.append("     explicit mention. If one is missing, flag it.")
    lines.append("  4. Enforce the token budget — trim or compact if response is overlength.")
    lines.append("  5. Do NOT add new factual claims not in the original response.")
    lines.append("=== END ROUTING CAPSULE ===")
    return "\n".join(lines)


# ── Out-of-scope fast path ─────────────────────────────────────────────────────
def _out_of_scope_result(query: str, note: str = "") -> dict:
    return {
        "intent":             "OUT_OF_SCOPE",
        "gene_ids":           [],
        "agents":             [],
        "stress_filter":      None,
        "regulation_filter":  None,
        "n_genes_requested":  None,
        "output_format":      "NONE",
        "required_sections":  [],
        "token_budget":       "SHORT",
        "routing_capsule":    "",
        "out_of_scope_response": _OUT_OF_SCOPE_RESPONSE,
        "router_note":        note or f"[AI_ROUTER] Query '{query}' is out of scope.",
    }


# ── Helpers ────────────────────────────────────────────────────────────────────
def _format_gene_id(raw: str) -> str:
    """Normalise a raw regex match to canonical Ca_XXXXX format."""
    digits = re.sub(r"[^0-9]", "", raw).zfill(5)
    return f"Ca_{digits}"


def _normalise_gene_ids(raw_list: list) -> list:
    result = []
    for item in raw_list:
        m = _GENE_ID_RE.search(str(item))
        if m:
            result.append(_format_gene_id(m.group()))
    return result


def _fallback_route(query: str, reason: str = "") -> dict:
    """Fall back to pattern-based semantic router when AI routing fails."""
    from modules.semantic_router import route_query as pattern_route
    result = pattern_route(query)

    # Quick scope check on fallback — reject obvious out-of-scope
    if not _IN_SCOPE_HINTS.search(query) and not _GENE_ID_RE.search(query):
        return _out_of_scope_result(
            query,
            note=f"[FALLBACK_ROUTER] No genomics keywords detected. Treating as OUT_OF_SCOPE.",
        )

    result.setdefault("stress_filter", None)
    result.setdefault("regulation_filter", None)
    result.setdefault("n_genes_requested", None)
    result.setdefault("output_format", "FULL_PROFILE")
    result.setdefault("required_sections", [])
    result.setdefault("token_budget", "LONG")

    gene_ids = result.get("gene_ids", [])
    result["routing_capsule"] = _build_routing_capsule(
        intent            = result.get("intent", "GENE_PROFILE"),
        gene_ids          = gene_ids,
        required_sections = result["required_sections"],
        token_budget      = result["token_budget"],
        output_format     = result["output_format"],
        query             = query,
    )

    prefix = f"[FALLBACK_ROUTER] AI routing failed ({reason}). " if reason else "[FALLBACK_ROUTER] "
    result["router_note"] = prefix + result.get("router_note", "")
    return result
