# Chickpea Stress-Responsive Genes (SRG) RAG Pipeline CLI - Project Completion Walkthrough

## Status

- Project documentation finalized on April 21, 2026.
- This document captures representative behavior and architecture for the final pipeline state.

## The Three-AI Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  AI-1  ROUTER   (fast, small model)                 │
│  • Scope gate — reject non-genomics queries         │
│  • Classify intent (GENE_PROFILE / GENE_LIST / ...) │
│  • Extract all gene IDs (Ca, LOC, symbol)           │
│  • Build routing capsule → sent to AI-3             │
│  • Set output_format + token_budget                 │
└──────────────┬──────────────────────────────────────┘
               │ routing_capsule (instructions for AI-3)
               │
    ┌──────────▼──────────┐
    │   Data Retrieval    │   ← gene_collector.py
    │  (no LLM, pure CSV) │     All Ca packets in one pass
    │  • Expression FPKM  │     (multi-ID: one packet per gene)
    │  • Log2FC + UP/DOWN │
    │  • Stress 3-states  │
    │  • Peptide sequence │
    └──────────┬──────────┘
               │ context block(s)
               ▼
┌─────────────────────────────────────────────────────┐
│  AI-2  ANALYST  (large model, main LLM call)        │
│  • Receives: intent-tuned system prompt             │
│      FULL_PROFILE → all 6 sections                  │
│      COMPACT_LIST → 3 sections only (no phantoms)   │
│      FOCUSED      → only requested sections         │
│  • MULTI-GENE: one data subsection per gene         │
│  • RULE: never include "No data" sections           │
└──────────────┬──────────────────────────────────────┘
               │ raw_response
               │
    ┌──────────▼─────────────────────────────────────┐
    │  AI-3  VALIDATOR  (reads routing_capsule)      │
    │  ① Section check  — only required sections      │
    │     remove extras / "No data" sections          │
    │  ② Gene coverage  — every expected ID present?  │
    │     flag missing; do NOT fabricate              │
    │  ③ Token budget   — trim prose if COMPACT/SHORT │
    │  ④ Table format   — valid Markdown pipe syntax  │
    │  ⑤ No fabrication — never add new facts         │
    └──────────┬─────────────────────────────────────┘
               │ validated_response
               ▼
          Terminal output
```

---

## Five Representative Query Scenarios

### Query 1 — Out-of-Scope Rejection

```
Query> what is 5 times 59
```

**AI-1 Router:**
- Scope gate fires: no genomics keywords, no Ca_ID
- `intent = OUT_OF_SCOPE` → immediate exit, zero data retrieval
- No AI-2 or AI-3 calls made (zero token spend)

**Output:**
```
⚠  OUT OF SCOPE
══════════════════════════════════════════
This pipeline is for chickpea stress-responsive genes analysis.
Your question appears to be outside this scope.
Please ask about specific genes, stress responses,
expression data, or peptide sequences.
```

**What changed vs before:** Previously the pipeline could misroute this as `GENE_LIST`, retrieve unrelated genes, and spend tokens on unnecessary sections.

---

### Query 2 — Simple Gene List (COMPACT_LIST)

```
Query> Give me 5 drought-responsive genes
```

**AI-1 Router:**
```json
{
  "intent": "GENE_LIST",
  "output_format": "COMPACT_LIST",
  "required_sections": ["Summary", "Stress Classification", "Biological Insights"],
  "token_budget": "MEDIUM"
}
```
Routing capsule to AI-3: *"REMOVE any section not in required list. Remove 'No data' sections."*

**AI-2 Analyst receives prompt:**
```
⚡ DO NOT include: Expression Evidence tables, Sequence Analysis,
   Confidence Assessment.
   These have no data for list queries and only waste tokens.
```

**Output (compact - no phantom sections):**
```markdown
## Summary
5 drought-responsive genes retrieved from the Stress Binary Matrix.
All are co-responsive to salinity, suggesting shared osmotic stress pathways.

## Stress Classification
| Gene ID   | Responsive Stresses       | Cold | Drought | Salinity | Heat |
|-----------|---------------------------|:----:|:-------:|:--------:|:----:|
| Ca_00999  | Drought, Salinity, Heat   |  0   |    1    |    1     |  1   |
| Ca_19295  | Drought, Salinity, Heat   |  0   |    1    |    1     |  1   |
| Ca_15398  | Cold, Drought, Salinity   |  1   |    1    |    1     |  0   |
...

## Biological Insights
These genes likely encode components of osmotic adjustment pathways...
```

**What changed:** No "Expression Evidence - No data" section. No "Sequence Analysis - not available" section. No "Confidence Assessment - LOW because no data" section. Output is significantly shorter and more informative.

---

### Query 3 — Single Gene Profile (FULL_PROFILE)

```
Query> Provide insights into Ca_00999 — is it drought responsive?
```

**AI-1 Router:**
```json
{
  "intent": "GENE_PROFILE",
  "gene_ids": ["Ca_00999"],
  "output_format": "FULL_PROFILE",
  "required_sections": ["Summary","Expression Evidence","Stress Classification",
                        "Sequence Analysis","Confidence Assessment","Biological Insights"],
  "token_budget": "LONG"
}
```

**Data retrieved** (gene_collector, no LLM):
- 44 expression pairs across 14 files (Drought: 6 pairs, 3 DOWNREGULATED in shoot)
- Stress states: Drought=RESPONSIVE, Salinity=RESPONSIVE, Heat=RESPONSIVE, Cold=NOT_RESPONSIVE
- Peptide: 163 aa, 6.7% Pro, 2.5% Cys

**AI-3 Validator checks:**
- ✓ All 6 required sections present
- ✓ Gene Ca_00999 addressed in every section
- ✓ No phantom "No data" sections (all have real data)
- ✓ Token budget: LONG → no trimming needed

---

### Query 4 — Multi-ID (Two Genes)

```
Query> Compare Ca_00001 and Ca_00999 under salinity
```

**AI-1 Router detects two IDs:**
```json
{
  "intent": "COMPARISON",
  "gene_ids": ["Ca_00001", "Ca_00999"],
  "output_format": "FULL_PROFILE",
  "token_budget": "LONG"
}
```

**Routing capsule to AI-3:**
```
Expected gene IDs: Ca_00001, Ca_00999
  → Validator MUST check: every gene ID above is addressed in the response.
```

**Data retrieval:**
- Ca_00001: 20 pairs, in Individual Files, NOT in Stress Matrix → NOT_RESPONSIVE (all stresses)
- Ca_00999: 44 pairs, in Stress Matrix → Drought/Salinity/Heat=RESPONSIVE

**AI-2 prompt includes:**
```
═══ MULTI-GENE QUERY ═══
This query covers 2 genes: Ca_00001, Ca_00999
You MUST address EACH gene individually with its own data subsection.
```

**AI-3 Validator:**
- Checks Ca_00001 and Ca_00999 are both addressed
- If one were missing → adds `[Gene Ca_00001: data not retrieved in this response]`

---

### Query 5 — LOC ID Input

```
Query> What do we know about LOC101488545?
```

**Router normalises with `_GENE_ID_RE`:**
- `LOC101488545` detected → will be resolved before data retrieval

**id_mapper.py:**
```
LOC101488545 → Ca_00003  (via mapping.csv)
```

**Output header:**
```
Gene: Ca_00003  |  Intent: GENE_PROFILE | Format: FULL_PROFILE  |  Validated: yes
External ID: LOC101488545
```

---

## The Routing Capsule - Message from AI-1 to AI-3

This is the key new mechanism. AI-1 writes explicit instructions that AI-3 reads:

```
=== ROUTING CAPSULE (from AI-1 Router to AI-3 Validator) ===
Original query   : Give me 5 drought-responsive genes
Intent           : GENE_LIST
Output format    : COMPACT_LIST
Token budget     : MEDIUM
Expected gene IDs: none (gene list query — IDs chosen by gene_search_agent)
Required sections: Summary, Stress Classification, Biological Insights
  → Validator MUST check: all required sections present and non-trivial.
Length rule      : Focused response (200-500 words). Only required sections.

VALIDATOR RULES:
  1. Do NOT add sections not in Required sections list.
  2. Do NOT include sections that say 'No data available' — omit them.
  3. If gene IDs listed, verify each gets at least one data point.
  4. Enforce token budget — trim prose if COMPACT/SHORT.
  5. Do NOT add new factual claims not in the original.
=== END ROUTING CAPSULE ===
```

AI-3 uses this to surgically fix only what fails validation rather than rewriting the full answer.

---

## Three-State Stress Summary (for LLM context)

| Gene | In Expr Files? | In Matrix? | Cold | Drought | Salinity | Heat |
|---|---|---|---|---|---|---|
| `Ca_00999` | ✓ (14 files) | ✓ | NOT_RESPONSIVE | **RESPONSIVE** | **RESPONSIVE** | **RESPONSIVE** |
| `Ca_00001` | ✓ (8 files) | ✗ | NOT_RESPONSIVE | NOT_RESPONSIVE | NOT_RESPONSIVE | NOT_RESPONSIVE |
| `Ca_00000` | ✗ (gap) | ✗ | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

The LLM now receives this as precise factual context — never conflates UNKNOWN with NOT_RESPONSIVE.

---

## Quick Command Reference

```bash
# Interactive mode
python3 pipeline.py

# Single gene
python3 pipeline.py --gene Ca_00999

# Via LOC ID
python3 pipeline.py --gene LOC101511858

# Via gene symbol
python3 pipeline.py --gene ARF1

# Multi-query shorthand
python3 pipeline.py --query "Compare Ca_00001 and Ca_00999 under salinity"

# Verbose (see all 3 AI inputs/outputs)
python3 pipeline.py --gene Ca_00999 --verbose

# Show before/after validator comparison
python3 pipeline.py --gene Ca_00999 --show-raw
```

## Web GUI

The pipeline is also accessible through a web interface built with FastAPI (backend) and Vite/TypeScript (frontend).

```bash
cd gui && bash run.sh
# Backend  → http://localhost:7860
# Frontend → http://localhost:5173
```

The GUI wraps the same `run_pipeline()` function and streams results via Server-Sent Events (SSE). The frontend renders Markdown cards with interactive features not available in the CLI:

- Real-time stage progress panel (6 stages with spinners)
- Log2FC auto-coloring in expression tables (green/red/amber)
- Gene ID auto-highlighting as inline badges
- GEO/BioProject accession IDs rendered as clickable NCBI links
- SVG diverging bar charts generated from expression tables
- In-session chat history sidebar
- Frosted-glass light theme with polka-dot background

---

## Recent feature additions (April 28, 2026)

### Biochemical property profiling

`biochem_properties.py` provides instant CSV lookup from `BiochemicalProperties.csv` (28k+ entries). For each gene with a peptide sequence, the LLM receives:

- Total amino acids, molecular weight (Da), theoretical pI
- Instability index (with Stable/Unstable classification)
- Aliphatic index, GRAVY (hydrophobicity)
- Atomic composition: C, H, N, O, S atom counts

The LLM system prompt includes interpretation guidance so the analysis explains what each metric means biologically (e.g., negative GRAVY indicates a hydrophilic protein likely localized in aqueous environments).

### GEO/BioProject data provenance

Each stress type is mapped to its source RNA-seq dataset accession IDs. These appear in expression table Source columns and as clickable NCBI links in the GUI. The mapping:

| Stress | Sources |
|---|---|
| Heat | PRJNA748749 |
| Cold | GSE53711 |
| Drought | GSE53711, GSE104609, GSE193077 |
| Salinity | GSE53711, GSE70377, GSE110127, GSE204727 |

### SVG diverging bar charts

The frontend generates SVG butterfly charts from rendered expression tables. Each bar extends left (red, downregulated) or right (green, upregulated) from a central zero axis. This provides an immediate visual summary of expression direction and magnitude per tissue/genotype.

### Randomized gene list search

Gene list queries now use tier-weighted random sampling. Candidates are grouped by `Num_Stresses` (3-stress > 2-stress > 1-stress), and within each tier, genes are randomly sampled. This prevents the same top-N results from appearing every time, improving gene discovery for researchers exploring the dataset.

---

## Completion summary

- Scope-aware routing prevents irrelevant answers.
- Multi-ID handling is enforced by validator coverage checks.
- Intent-aware output formats reduce token waste and avoid phantom sections.
- Three-state stress logic keeps UNKNOWN and NOT_RESPONSIVE semantically distinct.
- Biochemical protein properties provide evidence-based sequence characterization.
- GEO accession provenance traces every expression value to its source dataset.
- Interactive GUI makes the pipeline accessible to non-technical researchers.
- Documentation covers architecture, datasets, CLI reference, development workflow, and this walkthrough.

*Last updated: April 28, 2026.*
