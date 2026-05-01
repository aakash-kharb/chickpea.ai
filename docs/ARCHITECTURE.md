# Architecture

## Overview

The system has two interfaces (CLI and GUI) sharing a common Python pipeline that performs chickpea stress-responsive gene analysis using Retrieval Augmented Generation (RAG).

High-level flow:

1. Parse user query and optional gene override.
2. Route intent and scope with AI router (`ai_router.py`).
3. Resolve IDs to canonical `Ca_XXXXX` (`id_mapper.py`).
4. Retrieve gene data packet(s) (`gene_collector.py`) or gene list (`gene_search_agent.py`).
5. Enrich with biochemical properties (`biochem_properties.py`).
6. Build domain-aware prompt and generate analysis (LLM Phase 1).
7. Validate and repair response against router capsule (LLM Phase 2).
8. Render output: rich terminal (CLI) or Markdown card with SVG visualizations (GUI).

## Pipeline components

### `pipeline.py`

Main orchestrator and CLI entrypoint.

Responsibilities:

- project root/data path resolution
- loading domain knowledge (`knowledge/chickpea_knowledge.md`)
- routing + retrieval + analysis + validation orchestration
- terminal output formatting
- interactive REPL with conversation history (maintains context for follow-up questions)

Key CLI options:

- `--query`, `-q`: natural language query
- `--gene`, `-g`: explicit gene ID override
- `--verbose`, `-v`: print intermediate context
- `--json`: JSON output mode
- `--show-raw`: show pre-validation output

### `modules/ai_router.py`

AI-driven query router.

Responsibilities:

- classify intent (`GENE_PROFILE`, `GENE_LIST`, `EXPRESSION`, `SEQUENCE`, `STRESS_LABEL`, `COMPARISON`, `OUT_OF_SCOPE`)
- extract all gene IDs (multi-ID support) and inherit IDs from conversation history for follow-up queries
- define output format and required sections
- generate a routing capsule consumed by validator
- fallback to pattern router when JSON parse or LLM routing fails

### `modules/semantic_router.py`

Pattern/keyword router fallback.

Responsibilities:

- detect intent from regex patterns
- detect `Ca_XXXXX` IDs
- return minimal deterministic routing when AI routing is unavailable

### `modules/id_mapper.py`

Identifier normalization and mapping.

Responsibilities:

- normalize canonical IDs (`Ca_XXXXX`)
- map `LOC` and alias IDs to canonical IDs via `mapping.csv`
- support unresolved pass-through with explicit status notes

### `modules/gene_collector.py`

Unified data collector for one gene.

Responsibilities:

- expression extraction from all individual stress files
- Log2FC computation: `log2((stress + 1) / (control + 1))`
- regulation class labels (`UPREGULATED`, `DOWNREGULATED`, `NOT_SIGNIFICANT`)
- peptide lookup from `Ca_Peptide_Sequences.csv`
- biochemical property enrichment (delegates to `biochem_properties.py`)
- GEO/BioProject accession mapping per stress type
- three-state stress classification using expression presence + binary matrix
- formatting helper functions for prompt contexts and reports

Three-state semantics:

- `RESPONSIVE`: in expression files and matrix label `1`
- `NOT_RESPONSIVE`: expression observed but matrix is `0` or absent
- `UNKNOWN`: no expression records in individual files

### `modules/biochem_properties.py`

Biochemical property lookup module.

Responsibilities:

- LRU-cached CSV lookup from `BiochemicalProperties.csv` (28k+ rows)
- returns MW, pI, instability index, aliphatic index, GRAVY, and atomic composition (C/H/N/O/S)
- no external bioinformatics dependencies (pure CSV lookup)
- provides formatted context strings for LLM prompts

### `modules/gene_search_agent.py`

List-query retrieval agent.

Responsibilities:

- filter genes by stress labels from `Stress_Binary_Matrix.csv`
- optional regulation filtering (if expression agent is available)
- randomized tier-weighted sampling within `Num_Stresses` groups (multi-stress genes prioritized, but selection is non-deterministic within tiers for gene discovery variety)

### `modules/llm_interface.py`

Backend abstraction layer for LLM calls.

Responsibilities:

- centralize backend handling (`groq` or `ollama`)
- expose standard and model-specific request functions
- report active backend details for CLI metadata

## GUI architecture

```text
gui/
├── backend/          ← FastAPI (Python)
│   └── app.py        ← SSE endpoint wrapping pipeline.run_pipeline()
├── frontend/         ← Vite + TypeScript (no framework)
│   ├── index.html    ← App shell: sidebar + main area + input bar
│   └── src/
│       ├── main.ts       ← App entry: event handling, history
│       ├── api.ts        ← SSE client + REST helpers
│       ├── stages.ts     ← Stage progress panel (6 stages, spinner)
│       ├── renderer.ts   ← PipelineResult → DOM (marked.js, Log2FC coloring,
│       │                    GEO accession linkification)
│       ├── heatmap.ts    ← SVG diverging bar chart generator
│       ├── genepicker.ts ← Floating gene ID / example query popup
│       ├── types.ts      ← Shared TS interfaces
│       └── style.css     ← Full design system (frosted-glass light theme)
└── run.sh            ← One-command dev launcher (backend :7860 + frontend :5173)
```

Frontend features:

- `heatmap.ts`: Parses rendered expression tables, generates SVG diverging bar charts (butterfly charts) with green gradient (upregulated) and red gradient (downregulated) bars
- `renderer.ts`: Converts GEO/BioProject accession IDs (GSE..., PRJNA...) into clickable NCBI links
- Frosted-glass design with CSS backdrop-filter, polka-dot background
- Real-time SSE stage panel with 6 pipeline stages
- In-session chat history (sidebar)

SSE event flow:

1. User submits query → `POST /api/query`
2. Backend fires pipeline in a thread → emits `stage` events → emits `result` event
3. Frontend renders stage panel in real time → on `result`: renders Markdown card + SVG heatmaps

## Dataflow diagram

```text
User Query
   |
   v
AI Router (scope + intent + required sections)
   |
   +--> OUT_OF_SCOPE -> immediate response
   |
   v
ID Resolver (Ca/LOC/symbol -> Ca_XXXXX)
   |
   +--> Gene List path -> gene_search_agent (randomized) -> list context
   |
   +--> Gene Profile path -> gene_collector (per gene)
   |                          + biochem_properties lookup
   |                          + GEO accession mapping
   |                          -> merged context
   |
   v
LLM Phase 1 (analysis)
   |
   v
LLM Phase 2 (validator, routing capsule aware)
   |
   v
Output Router
   +--> CLI: Rich terminal renderer
   +--> GUI: Markdown card + SVG heatmaps + GEO links
```

## Error handling strategy

- router fallback when AI JSON is malformed
- out-of-scope guardrail in both AI and fallback path
- pass-through unresolved IDs instead of hard failure
- expression NaNs are skipped, never imputed
- optional rich output degrades gracefully to plain output
- heatmap generation fails silently if table parsing fails (fallback: no chart)
- biochem lookup returns None for unknown gene IDs (graceful skip)

## Testing scope

Current tests in `rag_pipeline/tests/test_agents.py` cover:

- ID mapping behavior
- Log2FC and regulation classification
- three-state stress logic
- semantic router intent extraction
- AI router mocked responses and fallbacks
- gene search stress filtering and sort behavior

## Related documents

- `PROJECT_COMPLETION_WALKTHROUGH.md`: end-to-end narrative of pipeline behavior.
- `DATASETS.md`: data asset schemas and interpretation rules.
- `Developer Notes/DecisionsAndRules.md`: all architectural decisions and coding conventions.
