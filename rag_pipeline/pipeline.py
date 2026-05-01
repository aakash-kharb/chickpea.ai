"""
pipeline.py  (v3 — Unified Gene Collector)
-------------------------------------------
Main orchestrator for the Chickpea Stress-Gene RAG pipeline.

Improvements over v2:
  ① Unified gene_collector — single retrieval pass replaces fragmented agents.
  ② ID resolution    — accepts Ca_XXXXX, LOC IDs, gene symbols (ARF1, NAC01…).
  ③ Three-state stress — RESPONSIVE / NOT_RESPONSIVE / UNKNOWN (not just 0/1).
  ④ Two-phase LLM     — Phase 1: rich analysis  |  Phase 2: validation & repair.
  ⑤ Gene-list support — "give me 3 cold-resistant genes" still works.
  ⑥ Rich terminal     — Markdown tables rendered properly (if `rich` installed).
  ⑦ --show-raw flag   — compare pre/post-validation output.

Usage:
    python pipeline.py
    python pipeline.py --gene Ca_00011 --verbose
    python pipeline.py --gene LOC101511858 --verbose          # LOC ID
    python pipeline.py --gene ARF1 --verbose                  # gene symbol
    python pipeline.py --query "Is Ca_00001 upregulated under salinity?"
    python pipeline.py --query "Give me 3 cold-resistant genes"
    python pipeline.py --gene Ca_00011 --verbose --show-raw
"""

import os
import re as _re
import sys
import argparse
import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

# ── Project root resolution ────────────────────────────────────────────────────
_PIPELINE_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _PIPELINE_DIR.parent.resolve()
sys.path.insert(0, str(_PIPELINE_DIR))

from modules.ai_router          import route_query_ai
from modules.id_mapper          import resolve_to_ca
from modules.gene_collector     import get_gene_packet, format_llm_context as collector_context
from modules.gene_search_agent  import format_gene_search_context
from modules.llm_interface      import get_llm_response, get_active_backend
from dotenv import load_dotenv

load_dotenv(_PIPELINE_DIR / ".env")

# ── Data paths ─────────────────────────────────────────────────────────────────
_INDIV_DIR    = _PROJECT_ROOT / "Individual Files"
_PEPTIDE_CSV  = _PROJECT_ROOT / "Ca_Peptide_Sequences.csv"
_STRESS_CSV   = _PROJECT_ROOT / "Stress_Binary_Matrix.csv"
_MAPPING_CSV  = _PROJECT_ROOT / "mapping.csv"
_BIOCHEM_CSV  = _PROJECT_ROOT / "BiochemicalProperties.csv"
_KNOWLEDGE_PATH  = _PIPELINE_DIR / "knowledge" / "chickpea_knowledge.md"

# ── Rich terminal output (optional) ───────────────────────────────────────────
try:
    from rich.console import Console as _RichConsole
    from rich.markdown import Markdown as _RichMarkdown
    from rich.live import Live as _RichLive
    from rich.spinner import Spinner as _RichSpinner  # noqa: F401  (kept for future use)
    from rich.text import Text as _RichText
    from rich.panel import Panel as _RichPanel
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False


# ── Conversation history (interactive REPL only) ──────────────────────────────
@dataclass
class ConversationTurn:
    """One turn of conversation history for follow-up context."""
    query: str
    gene_ids: list
    intent: str
    response_summary: str   # first ~300 chars of validated response
    routing_capsule: str


_conversation_history: deque = deque(maxlen=2)


# ── Stage progress tracker ─────────────────────────────────────────────────────
class _StageTracker:
    """
    Displays an animated spinner with a stage label while the pipeline runs.

    Uses rich.live so it erases itself cleanly before the final output appears.
    Degrades silently to a no-op when rich is not installed.

    Stage flow (mirrors pipeline execution order):
      routing   → Semantic & intent interpretation   (AI-1 LLM call)
      resolving → Resolving gene identifiers         (id_mapper)
      retrieving→ Data retrieval & packet assembly   (gene_collector / gene_search_agent)
      analysing → Agents running — LLM synthesis     (AI-2 LLM call)
      validating→ Routing capsule · output validation(AI-3 LLM call)
      rendering → Composing final response            (just before _print_result)
    """

    _STAGES = [
        ("routing",    "Semantic & intent interpretation"),
        ("resolving",  "Resolving gene identifiers"),
        ("retrieving", "Data retrieval & packet assembly"),
        ("analysing",  "Agents running  ·  LLM synthesis"),
        ("validating", "Routing capsule  ·  output validation"),
        ("rendering",  "Composing final response"),
    ]
    _STAGE_MAP = {k: i for i, (k, _) in enumerate(_STAGES)}

    _ACTIVE_STYLE  = "bold cyan"
    _DONE_STYLE    = "dim green"
    _PENDING_STYLE = "dim white"

    # Braille-dot spinner frames (no external dependency beyond rich)
    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        self._live    = None
        self._current = -1

    def __enter__(self):
        if not _RICH_AVAILABLE:
            return self
        self._console = _RichConsole(stderr=False)
        self._live    = _RichLive(
            self._render(frame=0),
            console            = self._console,
            refresh_per_second = 10,
            transient          = True,   # erases the block when closed
        )
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        if self._live:
            self._live.__exit__(*args)

    def advance(self, stage_key: str) -> None:
        """Move the tracker to *stage_key* and refresh the display."""
        if not _RICH_AVAILABLE or self._live is None:
            return
        self._current = self._STAGE_MAP.get(stage_key, self._current)
        self._live.update(self._render(frame=0))

    # ── Rendering ─────────────────────────────────────────────────────────────
    def _render(self, frame: int = 0) -> "_RichText":
        spinner_char = self._FRAMES[frame % len(self._FRAMES)]
        lines = _RichText()
        lines.append("\n")
        for i, (key, label) in enumerate(self._STAGES):
            if i < self._current:
                lines.append(f"  ✓  {label}\n", style=self._DONE_STYLE)
            elif i == self._current:
                lines.append(f"  {spinner_char}  {label}\n", style=self._ACTIVE_STYLE)
            else:
                lines.append(f"  ·  {label}\n", style=self._PENDING_STYLE)
        return lines


# ── Knowledge loader ───────────────────────────────────────────────────────────
def _load_knowledge() -> str:
    if _KNOWLEDGE_PATH.exists():
        return _KNOWLEDGE_PATH.read_text(encoding="utf-8")
    return "[Knowledge base not found — skipping domain context.]"


# ── Unified context assembly (gene_collector) ─────────────────────────────────
def _build_context(gene_id: str) -> str:
    """Single-pass retrieval for one resolved Ca_XXXXX gene ID."""
    packet = get_gene_packet(
        gene_id     = gene_id,
        indiv_dir   = _INDIV_DIR,
        peptide_csv = _PEPTIDE_CSV,
        stress_csv  = _STRESS_CSV,
        mapping_csv = _MAPPING_CSV,
        biochem_csv = _BIOCHEM_CSV,
    )
    return collector_context(packet)


def _build_gene_list_context(routing: dict) -> str:
    """Build context for GENE_LIST queries (no specific gene ID)."""
    return format_gene_search_context(
        stress_filter      = routing.get("stress_filter"),
        regulation_filter  = routing.get("regulation_filter"),
        n_genes            = routing.get("n_genes_requested") or 5,
        stress_matrix_path = str(_STRESS_CSV),
        indiv_dir          = str(_INDIV_DIR),
    )


# ── Phase-1 System Prompt — intent-aware ─────────────────────────────────────
def _build_analysis_system(knowledge: str, output_format: str = "FULL_PROFILE",
                           required_sections: list = None, gene_ids: list = None) -> str:
    """
    Build the Phase-1 (analysis) system prompt tailored to the routing intent.

    output_format   FULL_PROFILE  → all 6 sections mandatory
                    COMPACT_LIST  → Summary + Stress Classification + Biological Insights only
                    FOCUSED       → only the sections in required_sections
    """
    required_sections = required_sections or []
    gene_ids          = gene_ids or []

    # ── Section instructions per format ───────────────────────────────────────
    if output_format == "COMPACT_LIST":
        section_block = """
═══ OUTPUT FORMAT: COMPACT LIST ════════════════════════════════════════════════
This is a gene-list query. Write ONLY these sections — nothing else:

## Summary
1-2 sentences: how many genes found, which stresses they respond to.

## Stress Classification
A clean Markdown table:
| Gene ID | Responsive Stresses | Cold | Drought | Salinity | Heat |
|---------|--------------------:|:----:|:-------:|:--------:|:----:|
[one row per gene]
Then 2-3 sentences on what the pattern means collectively.

## Biological Insights
2-3 sentences on biological relevance and breeding potential.

⚡ DO NOT include: Expression Evidence tables, Sequence Analysis, Confidence Assessment.
   These sections have no data for list queries and would only waste tokens."""

    elif output_format == "FOCUSED" and required_sections:
        sec_list = ", ".join(f"## {s}" for s in required_sections)
        seq_instruction = ""
        if "Sequence Analysis" in required_sections:
            seq_instruction = """

⚡ SEQUENCE ANALYSIS RULE: When Sequence Analysis is a required section,
   you MUST include the ACTUAL full peptide sequence from the retrieved data
   inside a Markdown fenced code block (triple backticks). Do NOT just describe
   or summarise the sequence — show the full amino acid string. Also include
   the biochemical properties (MW, pI, GRAVY, etc.) from the retrieved data
   as a Markdown table with biological interpretation."""
        section_block = f"""
═══ OUTPUT FORMAT: FOCUSED ═════════════════════════════════════════════════════
Provide ONLY these sections: {sec_list}
Omit all other sections entirely — do not include them with placeholder text.
Within each section, be thorough and cite actual data values.{seq_instruction}"""

    else:  # FULL_PROFILE (default)
        section_block = """
═══ REQUIRED OUTPUT SECTIONS (FULL PROFILE) ════════════════════════════════════
Use these EXACT headers:

## Summary
2-4 sentence overview: gene identity, overall stress behaviour, key finding.

## Expression Evidence
For EACH stress type that has data:
### [StressType] Response
| Source | Tissue/Genotype | Ctrl FPKM | Stress FPKM | Log2FC | Status |
|--------|-----------------|-----------|-------------|--------|--------|
[ALL data rows — omit none]

After each expression table, leave a BLANK LINE then write the biological interpretation as a
regular paragraph (NOT inside a table row) starting with **Biological interpretation:**.
This must be a standalone paragraph below the table — never a table row.
ALWAYS put a blank line between the last table row and the interpretation paragraph.

## Stress Classification
- Responsive stresses (label=1): [list]
- Not responsive (label=0): [list]
- UNKNOWN (absent from Individual Files): [list]

**Note:** If discrepancies exist between binary label and expression evidence
(such as mixed responses under salinity and drought, which may indicate complex
regulatory mechanisms), discuss them in a separate paragraph below the lists.
This note MUST be on its own line/paragraph, NEVER appended to any bullet point.

## Sequence Analysis
- Length and protein class
- **IMPORTANT:** Always display the full peptide sequence inside a Markdown
  fenced code block (triple backticks). Never output it as inline plain text.
  The sequence will be provided in a code block in the data — preserve that format.

## Biochemical Properties
Interpret the pre-computed biochemical properties from the retrieved data:
- **Molecular Weight (Da)** — note size class (small peptide, medium, large protein)
- **Theoretical pI** — classify as acidic (<7), neutral (~7), or basic (>7); discuss charge at physiological pH
- **Instability Index** — if >40 classify as unstable; discuss implications for protein stability
- **Aliphatic Index** — higher values suggest thermostability; discuss relevance to heat stress tolerance
- **GRAVY** — negative = hydrophilic (likely cytoplasmic), positive = hydrophobic (membrane-associated)
- **Atomic Composition (C, H, N, O, S)** — note sulfur count as indicator of disulfide bond potential
Present the data as a clean Markdown table with biological interpretation.

## Confidence Assessment
**Level: HIGH / MODERATE / LOW**
Cite: number of independent experiments, consistency %, data completeness fraction.

## Biological Insights
2-3 sentences: role in stress response, pathway, agricultural / breeding relevance."""

    # ── Multi-gene instruction ─────────────────────────────────────────────────
    multi_gene_block = ""
    if len(gene_ids) > 1:
        ids_str = ", ".join(gene_ids)
        multi_gene_block = f"""
═══ MULTI-GENE QUERY ═══════════════════════════════════════════════════════════
This query covers {len(gene_ids)} genes: {ids_str}
You MUST address EACH gene individually with its own data subsection.
Do not merge or average across genes unless explicitly asked to compare."""

    return f"""You are a specialist bioinformatics AI for chickpea (Cicer arietinum) abiotic stress genomics.

Your task: produce a BIOLOGICALLY MEANINGFUL analysis of the gene data provided.

═══ CRITICAL RULES ═════════════════════════════════════════════════════════════
① NEVER fabricate expression values, sequences, or stress classifications.
② Use ALL expression data rows — do not summarise or skip rows.
③ NEVER include a section that only says "No data" or "not available".
   If data is absent for a section, OMIT that section entirely.
④ Every included section MUST have biological interpretation, not just numbers.
⑤ Tables must use proper Markdown pipe syntax.
{multi_gene_block}
{section_block}

═══ FINE-TUNING EXAMPLES ═══════════════════════════════════════════════════════

Good expression note: "Ca_00011 shows leaf-specific upregulation under heat (Log2FC +2.53
to +2.66 across 4 cultivars) while root expression is mixed/non-significant — consistent
with a heat-shock chaperone protecting photosynthetic tissue."

Good list summary: "5 genes responsive to drought were retrieved. All are also responsive
to salinity, suggesting overlap in osmotic stress pathways."

═══ DOMAIN KNOWLEDGE ═══════════════════════════════════════════════════════════
{knowledge}
"""


# ── Phase-2 System Prompt — capsule-aware validator ───────────────────────────
def _build_validator_system(routing_capsule: str) -> str:
    """
    Build the Phase-2 (validator) system prompt using the routing capsule
    produced by AI-1 (router) to know exactly what AI-2 was supposed to produce.
    """
    return f"""You are the quality-control agent (AI-3) for a chickpea genomics RAG pipeline.

AI-1 (Router) has provided you with a routing capsule that specifies exactly what
AI-2 (Analyst) was supposed to produce. Your job is to verify and repair the output.

{routing_capsule}

═══ YOUR VERIFICATION CHECKLIST ════════════════════════════════════════════════
① SCOPE CHECK: If routing says OUT_OF_SCOPE, ensure response politely declines
   without answering the non-genomics question.

② SECTION CHECK: Only the Required Sections listed in the capsule should be present.
   - Add any required section that is missing (with a [VALIDATOR ADDED] note).
   - REMOVE any extra section that is NOT in the required list.
   - REMOVE any section whose entire content is "No data", "Not available", or similar.

③ GENE COVERAGE: If Expected Gene IDs are listed, verify each ID is addressed.
   - If a gene is missing from the analysis, add a note: [Gene X: data not retrieved].
   - Do not fabricate data for a missing gene.

④ TOKEN BUDGET: Enforce the length rule from the capsule.
   - COMPACT_LIST / SHORT: trim verbose paragraphs, remove redundant sentences.
   - Do not trim actual data tables — only prose.

⑤ TABLE FORMAT: All Markdown tables must use proper pipe syntax with header rows.

⑥ NO FABRICATION: Do NOT add factual claims, numbers, or sequences not in the
   original analysis or the retrieved data above.

═══ ACTIONS ════════════════════════════════════════════════════════════════════
- If all checks pass → return the analysis UNCHANGED.
- If checks fail → fix ONLY the failing parts. Return the corrected full analysis.
- Return ONLY the final analysis text. No preamble like "Here is the corrected..."
"""


# ── Main pipeline ──────────────────────────────────────────────────────────────
def run_pipeline(
    query: str,
    gene_id: str = None,
    verbose: bool = False,
    _tracker: "_StageTracker | None" = None,
    conversation_history: list = None,
) -> dict:
    """
    Execute the three-AI RAG pipeline.

    AI-1 : Router    — scope gate, intent, routing capsule
    AI-2 : Analyst   — data retrieval + LLM synthesis (intent-aware prompt)
    AI-3 : Validator — uses routing capsule to verify section coverage,
                       gene ID coverage, token budget, table format

    Parameters
    ----------
    query   : str   Natural-language user question.
    gene_id : str   Optional Ca/LOC/symbol override (skips router gene extraction).
    verbose : bool  Print intermediate steps to stdout.
    conversation_history : list  Optional list of ConversationTurn for follow-ups.
    """
    # ═══════════════════════════════════════════════════════════════════════════
    # AI-1: Router
    # ═══════════════════════════════════════════════════════════════════════════
    if _tracker:
        _tracker.advance("routing")
    routing = route_query_ai(query, conversation_history=conversation_history or [])
    if verbose:
        print(f"\n{routing['router_note']}")

    intent          = routing["intent"]
    agents          = routing["agents"]
    output_format   = routing.get("output_format", "FULL_PROFILE")
    req_sections    = routing.get("required_sections", [])
    routing_capsule = routing.get("routing_capsule", "")
    is_list_query   = (intent == "GENE_LIST" or "gene_search" in agents)

    # ── OUT_OF_SCOPE fast exit ─────────────────────────────────────────────────
    if intent == "OUT_OF_SCOPE":
        oos_response = routing.get("out_of_scope_response", "Query is out of scope.")
        if verbose:
            print("[SCOPE GATE] Query rejected as out-of-scope.")
        return {
            "gene_id":            "[out of scope]",
            "intent":             "OUT_OF_SCOPE",
            "agents_used":        [],
            "context":            "",
            "llm_response":       oos_response,
            "llm_raw_response":   oos_response,
            "validation_applied": False,
            "router_note":        routing["router_note"],
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # Resolve gene IDs  (multi-ID support)
    # ═══════════════════════════════════════════════════════════════════════════
    if _tracker:
        _tracker.advance("resolving")
    if not is_list_query:
        # Collect ALL gene IDs the router detected (multi-ID)
        detected_ids = routing.get("gene_ids", [])
        if gene_id is not None:
            detected_ids = [gene_id] + [x for x in detected_ids if x != gene_id]

        if not detected_ids:
            return {
                "error": (
                    "No gene ID found in query. "
                    "Include a Ca_XXXXX, LOC, or gene symbol, "
                    "use --gene explicitly, or ask for a gene list."
                )
            }

        # Resolve every detected ID to canonical Ca_XXXXX
        resolved_ids = []
        id_notes     = []
        for raw_id in detected_ids:
            id_map = resolve_to_ca(raw_id, str(_MAPPING_CSV))
            resolved_ids.append(id_map["ca_id"])
            if not id_map["was_ca"]:
                id_notes.append(id_map["note"])

        if verbose:
            for orig, resolved in zip(detected_ids, resolved_ids):
                arrow = f" → {resolved}" if orig.upper() != resolved.upper() else ""
                print(f"  ID: {orig}{arrow}")
            print(f"  Agents: {agents}\n")

        # Primary gene_id (first one) for labelling; context covers all
        gene_id = resolved_ids[0]

    else:
        resolved_ids = []
        id_notes     = []

    # ═══════════════════════════════════════════════════════════════════════════
    # AI-2 Data retrieval
    # ═══════════════════════════════════════════════════════════════════════════
    if _tracker:
        _tracker.advance("retrieving")
    if is_list_query:
        context = _build_gene_list_context(routing)
        gene_id = gene_id or "[gene list query]"
    else:
        # Retrieve packet for EACH resolved ID, concatenate contexts
        context_blocks = []
        for rid in resolved_ids:
            context_blocks.append(_build_context(rid))
        context = "\n\n".join(context_blocks)

    if verbose:
        print("─── Retrieved Context ───────────────────────────────────────────")
        print(context[:2000] + ("..." if len(context) > 2000 else ""))
        print("─────────────────────────────────────────────────────────────────\n")

    # ═══════════════════════════════════════════════════════════════════════════
    # AI-2: Phase-1 LLM — Intent-aware analysis
    # ═══════════════════════════════════════════════════════════════════════════
    knowledge = _load_knowledge()
    system_p1 = _build_analysis_system(
        knowledge      = knowledge,
        output_format  = output_format,
        required_sections = req_sections,
        gene_ids       = resolved_ids,
    )
    gene_label = ", ".join(resolved_ids) if resolved_ids else gene_id

    # ── Conversation context for follow-up queries ─────────────────────────────
    conv_context_block = ""
    if conversation_history:
        prev = conversation_history[-1]  # most recent turn
        conv_context_block = (
            f"=== CONVERSATION CONTEXT (previous turn) ===\n"
            f"Previous question: {prev.query}\n"
            f"Previous gene IDs: {', '.join(prev.gene_ids) if prev.gene_ids else 'none'}\n"
            f"Previous answer (summary): {prev.response_summary}\n"
            f"=== END CONVERSATION CONTEXT ===\n\n"
        )

    user_p1 = (
        f"{conv_context_block}"
        f"User Query: {query}\n\n"
        f"Gene(s) of Interest: {gene_label}\n\n"
        f"Retrieved Data (use ALL rows in tables):\n{context}"
    )

    if verbose:
        print(f"[AI-2 Phase 1] Calling {get_active_backend()} | format={output_format}")

    if _tracker:
        _tracker.advance("analysing")
    raw_response = get_llm_response(system_p1, user_p1)

    # ═══════════════════════════════════════════════════════════════════════════
    # AI-3: Phase-2 LLM — Capsule-aware Validator
    # ═══════════════════════════════════════════════════════════════════════════
    if _tracker:
        _tracker.advance("validating")
    if verbose:
        print("[AI-3 Validator] Checking with routing capsule …")

    validator_system = _build_validator_system(routing_capsule)
    validation_prompt = (
        f"Retrieved data provided to AI-2:\n{context}\n\n"
        f"AI-2 response to validate:\n{raw_response}"
    )
    validated_response = get_llm_response(validator_system, validation_prompt)
    validation_applied = validated_response.strip() != raw_response.strip()

    return {
        "gene_id":            gene_label,
        "intent":             intent,
        "output_format":      output_format,
        "agents_used":        agents,
        "context":            context,
        "llm_response":       validated_response,
        "llm_raw_response":   raw_response,
        "validation_applied": validation_applied,
        "router_note":        routing["router_note"],
        "routing_capsule":    routing_capsule,
    }


# ── Post-processing helpers ───────────────────────────────────────────────────
# Regex to detect fenced code blocks whose content is purely amino acid letters
_PEPTIDE_BLOCK_RE = _re.compile(
    r'```[^\n]*\n([A-Z\n]+)\n```',
    _re.MULTILINE,
)


def _fix_table_notes(md_text: str) -> str:
    """
    Detect table rows where only the first cell has content (typically
    'Biological interpretation' or 'Note') and all other cells are empty.
    Convert them to standalone paragraphs so Rich renders them at full
    terminal width instead of cramming text into a narrow column.

    Also detects 'Biological interpretation:' appearing as a regular line
    immediately after a table row (no blank line) and inserts separation.
    """
    lines = md_text.split('\n')
    result = []
    prev_was_table_row = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('|') and stripped.endswith('|'):
            # Split the row into cells (strip outer pipes first)
            inner = stripped[1:-1]  # remove leading/trailing |
            cells = [c.strip() for c in inner.split('|')]
            first_cell = cells[0] if cells else ''
            other_cells = cells[1:] if len(cells) > 1 else []
            first_lower = first_cell.lower().lstrip('*')
            is_note = (
                first_lower.startswith('biological interpretation')
                or first_lower.startswith('note:')
                or first_lower.startswith('note ')
                or first_lower.startswith('**note')
            )
            all_others_empty = all(not c for c in other_cells)
            if is_note and all_others_empty and first_cell:
                result.append('')
                result.append(first_cell)
                result.append('')
                prev_was_table_row = False
                continue
            prev_was_table_row = True
            result.append(line)
            continue

        # Non-table line: check if it's a bio interpretation right after a table
        low = stripped.lower().lstrip('*')
        is_bio_note = (
            low.startswith('biological interpretation')
            or low.startswith('note:')
            or low.startswith('**biological interpretation')
        )
        if prev_was_table_row and is_bio_note and stripped:
            result.append('')  # force blank line to break out of table
            result.append(stripped)
            result.append('')
            prev_was_table_row = False
            continue

        prev_was_table_row = False
        result.append(line)
    return '\n'.join(result)


def _render_rich_response(console: "_RichConsole", md_text: str) -> None:
    """
    Render a Markdown response with Rich, but handle peptide sequence code
    blocks specially: extract them from the Markdown, render them in a
    word-wrapped Panel so the sequence flows naturally at terminal width.
    """
    # Split the response around peptide code blocks
    parts = _PEPTIDE_BLOCK_RE.split(md_text)
    # parts alternates: [markdown, peptide_seq, markdown, peptide_seq, ...]
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Regular markdown content
            stripped = part.strip()
            if stripped:
                console.print(_RichMarkdown(stripped))
        else:
            # Peptide sequence content — join into single line, wrap in Panel
            seq = part.replace('\n', '')
            seq_text = _RichText(seq, style="bold green")
            seq_text.no_wrap = False
            console.print(_RichPanel(
                seq_text,
                title="Peptide Sequence",
                title_align="left",
                border_style="dim cyan",
                padding=(0, 1),
            ))


# ── Output rendering ───────────────────────────────────────────────────────────
def _print_result(result: dict, show_raw: bool = False) -> None:
    """Pretty-print pipeline result — uses rich if available, plain text otherwise."""

    # OUT_OF_SCOPE gets a clean, minimal display
    if result.get("intent") == "OUT_OF_SCOPE":
        if _RICH_AVAILABLE:
            console = _RichConsole()
            console.print()
            console.rule("[bold yellow]⚠ Out of Scope[/bold yellow]")
            console.print(_RichMarkdown(result["llm_response"]))
            console.rule()
        else:
            print("\n" + "=" * 72)
            print("⚠  OUT OF SCOPE")
            print("=" * 72)
            print(result["llm_response"])
            print("=" * 72 + "\n")
        return

    fmt    = result.get("output_format", "")
    fmt_tag = f" | Format: {fmt}" if fmt else ""
    meta = (
        f"Gene: {result['gene_id']}  |  "
        f"Intent: {result['intent']}{fmt_tag}  |  "
        f"Validated: {'yes' if result.get('validation_applied') else 'no'}"
    )

    if _RICH_AVAILABLE:
        console = _RichConsole()
        console.print()
        console.rule(meta)
        display_text = _fix_table_notes(result["llm_response"])
        _render_rich_response(console, display_text)
        console.rule()
        console.print()
        if show_raw and result.get("validation_applied"):
            console.rule("Pre-validation output")
            raw_display = _fix_table_notes(result.get("llm_raw_response", ""))
            _render_rich_response(console, raw_display)
            console.rule()
    else:
        sep = "=" * 72
        print(f"\n{sep}")
        print(meta)
        print(sep)
        print(result["llm_response"])
        print(sep + "\n")
        if show_raw and result.get("validation_applied"):
            print("── Pre-validation output ─────────────────────────────────────────")
            print(result.get("llm_raw_response", ""))
            print("──────────────────────────────────────────────────────────────────\n")


# ── CLI ────────────────────────────────────────────────────────────────────────
def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Chickpea Stress-Gene RAG Pipeline v3 — Scope-aware · Multi-ID · Intent-tuned"
    )
    parser.add_argument("--query",    "-q", type=str, default=None,
                        help="Natural-language query")
    parser.add_argument("--gene",     "-g", type=str, default=None,
                        help="Gene ID override (e.g. Ca_00011)")
    parser.add_argument("--verbose",  "-v", action="store_true",
                        help="Print intermediate steps")
    parser.add_argument("--json",           action="store_true",
                        help="Output full result as JSON")
    parser.add_argument("--show-raw",       action="store_true",
                        help="Show pre-validation response alongside final output")
    args = parser.parse_args()

    query   = args.query
    gene_id = args.gene

    # ── Interactive REPL ───────────────────────────────────────────────────────
    if query is None and gene_id is None:
        print("Chickpea Stress-Gene RAG Pipeline v3 — Interactive Mode")
        print(f"Backend : {get_active_backend()}")
        print(f"Rich    : {'enabled' if _RICH_AVAILABLE else 'not installed (pip install rich)'}")
        print("Scope   : chickpea transcriptomics only (out-of-scope queries declined)")
        print("Type 'exit' to quit.\n")
        while True:
            try:
                query = input("Query> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            if query.lower() in ("exit", "quit", "q"):
                break
            if not query:
                continue

            with _StageTracker() as tracker:
                result = run_pipeline(
                    query,
                    verbose=args.verbose,
                    _tracker=tracker,
                    conversation_history=list(_conversation_history),
                )
                if "error" not in result:
                    tracker.advance("rendering")
            if "error" in result:
                print(f"\n[ERROR] {result['error']}\n")
            else:
                _print_result(result, show_raw=args.show_raw)
                # ── Push to conversation history ──────────────────────
                resp_text = result.get("llm_response", "")
                summary = resp_text[:300].rsplit(" ", 1)[0] if len(resp_text) > 300 else resp_text
                _conversation_history.append(ConversationTurn(
                    query=query,
                    gene_ids=(
                        [g.strip() for g in result.get("gene_id", "").split(",")]
                        if result.get("gene_id") and result["gene_id"] != "[gene list query]"
                        else []
                    ),
                    intent=result.get("intent", ""),
                    response_summary=summary,
                    routing_capsule=result.get("routing_capsule", ""),
                ))
        return

    # ── Single-query mode ──────────────────────────────────────────────────────
    if query is None:
        query = f"Provide a comprehensive profile of gene {gene_id}"

    result = run_pipeline(query, gene_id=gene_id, verbose=args.verbose)

    if "error" in result:
        print(f"[ERROR] {result['error']}")
        sys.exit(1)

    if args.json:
        out = {k: v for k, v in result.items() if k not in ("context", "llm_raw_response")}
        print(json.dumps(out, indent=2))
    else:
        _print_result(result, show_raw=args.show_raw)


if __name__ == "__main__":
    _cli()
