# Everything Information — Chickpea SRG RAG Pipeline GUI

> **Purpose:** One-stop reference for any developer joining the project. Answers "what are we building and why?" in plain terms, then provides the technical crux of every layer.

---

## 1. What Is This Project?

**Chickpea SRG RAG Pipeline** is a domain-specific AI assistant for genomics researchers studying **Cicer arietinum (chickpea) stress-responsive genes (SRGs)**.

It answers natural-language questions about:
- Whether a gene is upregulated/downregulated under stress conditions
- Log2FC expression values across 14+ stress experiments
- Stress classification (RESPONSIVE / NOT_RESPONSIVE / UNKNOWN) for 4 stresses: Cold, Drought, Salinity, Heat
- Peptide sequences of genes
- Comparison of multiple genes
- Gene lists filtered by stress responsiveness

**Out-of-scope questions are intentionally rejected** — this is a specialized tool, not a general chatbot.

---

## 2. The Journey: CLI → GUI

- **Phase 1 (COMPLETE):** CLI pipeline (`rag_pipeline/pipeline.py`). Works via terminal commands.
- **Phase 2 (IN PROGRESS):** GUI — a web interface wrapping the same pipeline via a FastAPI backend and a Vite/TypeScript frontend.

The GUI goal is to make the pipeline accessible to non-technical researchers through a clean, chat-style web interface.

---

## 3. Three-AI Architecture (The Core)

```
User Query
    │
    ▼
AI-1 ROUTER (small, fast — e.g. llama-3.1-8b-instant via Groq)
  • Scope gate: reject non-genomics queries immediately
  • Classify intent: GENE_PROFILE | GENE_LIST | EXPRESSION | SEQUENCE |
                     STRESS_LABEL | COMPARISON | OUT_OF_SCOPE
  • Extract gene IDs (Ca_XXXXX, LOC..., gene symbols)
  • Produce routing_capsule → instructions for AI-3
  • Set output_format (FULL_PROFILE | COMPACT_LIST | FOCUSED)
  • Set token_budget (SHORT | MEDIUM | LONG)
    │
    ▼
DATA RETRIEVAL (no LLM — pure CSV/Python)
  • gene_collector.py: expression FPKM pairs, Log2FC, stress 3-states, peptides
  • gene_search_agent.py: for list queries (filter Stress_Binary_Matrix.csv)
  • id_mapper.py: Ca_XXXXX ↔ LOC... ↔ gene symbols via mapping.csv
    │
    ▼
AI-2 ANALYST (large — e.g. llama-3.3-70b-versatile via Groq)
  • Receives intent-tuned system prompt + real retrieved data
  • Generates biological analysis: expression evidence, stress classification,
    sequence analysis, confidence assessment, biological insights
  • RULE: never write "No data" sections — omit them
    │
    ▼
AI-3 VALIDATOR (large, uses routing_capsule from AI-1)
  • Checks required sections are present and non-trivial
  • Checks every expected gene ID is addressed
  • Enforces token budget (trims prose for COMPACT/SHORT)
  • Fixes table formatting
  • NEVER fabricates new facts
    │
    ▼
Output (CLI: rich terminal | GUI: rendered Markdown card)
```

---

## 4. Data Assets (Project Root)

| File | Rows | Purpose |
|---|---|---|
| `Stress_Binary_Matrix.csv` | 1,630 genes | Binary stress labels (0/1) per stress |
| `Ca_Peptide_Sequences.csv` | 28,269 entries | Peptide sequences per Ca_ID |
| `mapping.csv` | 27,078 rows | Ca_XXXXX ↔ Transcript ID ↔ LOC ID |
| `Individual Files/*.csv` | 15 files | Per-experiment FPKM expression matrices |

**Log2FC formula:** `log2((stress_FPKM + 1) / (control_FPKM + 1))`
**Regulation threshold:** ≥ +1.5 = UPREGULATED, ≤ −1.5 = DOWNREGULATED, else NOT_SIGNIFICANT

---

## 5. Three-State Stress Semantics

| State | Meaning |
|---|---|
| `RESPONSIVE` | Gene appears in expression files AND binary matrix label = 1 |
| `NOT_RESPONSIVE` | Expression observed in individual files BUT matrix = 0 or absent |
| `UNKNOWN` | No expression records at all in individual files |

> ⚠️ **Critical:** UNKNOWN ≠ NOT_RESPONSIVE. The LLM must never conflate these.

---

## 6. GUI Architecture

```
gui/
├── backend/          ← FastAPI (Python)
│   ├── app.py        ← SSE endpoint wrapping pipeline.run_pipeline()
│   └── requirements.txt
├── frontend/         ← Vite + TypeScript (no framework)
│   ├── index.html    ← App shell: sidebar + main area + input bar
│   └── src/
│       ├── main.ts       ← App entry: event handling, history skeleton
│       ├── api.ts        ← SSE client + REST helpers
│       ├── stages.ts     ← Stage progress panel (6 stages, spinner)
│       ├── renderer.ts   ← PipelineResult → DOM (marked.js, Log2FC coloring)
│       ├── genepicker.ts ← Floating gene ID / example query popup
│       ├── types.ts      ← Shared TS interfaces
│       └── style.css     ← Full design system (light theme, CSS variables)
└── run.sh            ← One-command dev launcher (backend :7860 + frontend :5173)
```

**SSE Event Flow:**
1. User submits query → `POST /api/query`
2. Backend fires pipeline in a thread → emits `stage` events (6 stages) → emits `result` event
3. Frontend renders stage panel in real time → on `result`: renders Markdown card

---

## 7. LLM Backends

| Backend | Config key | Notes |
|---|---|---|
| Groq | `LLM_BACKEND=groq` | Default. Uses `GROQ_API_KEY`. Fast, cloud-hosted. |
| Ollama | `LLM_BACKEND=ollama` | Local. Uses `OLLAMA_BASE_URL` + `OLLAMA_MODEL`. |

Config lives in `rag_pipeline/.env`.

---

## 8. Rules & Standards (from `rag_pipeline/rules.md`)

- Always normalize IDs to canonical `Ca_XXXXX`.
- No NaN imputation — skip missing expression values silently.
- Use Log2FC pseudo-count formula (not raw ratio).
- Route ALL LLM calls through `modules/llm_interface.py`.
- No hardcoded absolute paths.
- Keep modules independently testable.
- GUI: never break the SSE stream contract (`stage` → `result` | `error`).

---

## 9. Key Files Quick-Reference

| File | Role |
|---|---|
| `rag_pipeline/pipeline.py` | Main orchestrator — also exports `run_pipeline()` for GUI |
| `rag_pipeline/modules/ai_router.py` | Intent/scope/routing capsule |
| `rag_pipeline/modules/gene_collector.py` | Expression + stress + peptide + biochem retrieval |
| `rag_pipeline/modules/biochem_properties.py` | Biochemical property CSV lookup (MW, pI, GRAVY, etc.) |
| `rag_pipeline/modules/gene_search_agent.py` | List-query filtering + randomized sampling |
| `rag_pipeline/modules/id_mapper.py` | ID normalization |
| `rag_pipeline/modules/llm_interface.py` | Groq/Ollama abstraction |
| `gui/backend/app.py` | FastAPI SSE bridge |
| `gui/frontend/src/main.ts` | UI entry + event orchestration |
| `gui/frontend/src/renderer.ts` | Markdown + table + GEO link rendering |
| `gui/frontend/src/heatmap.ts` | SVG diverging bar chart generator |
| `gui/frontend/src/stages.ts` | Real-time stage progress panel |
| `gui/frontend/src/style.css` | Full design token system |

---

## 10. Current Status

- ✅ CLI pipeline: complete and documented.
- ✅ GUI backend (FastAPI + SSE): implemented.
- ✅ GUI frontend: complete (sidebar, stage panel, result cards, gene picker, chat history).
- ✅ Biochemical property profiling: CSV lookup integrated (no BioPython).
- ✅ GEO/BioProject data provenance: per-stress accession IDs in tables + clickable GUI links.
- ✅ SVG heatmaps: diverging bar charts auto-generated after expression tables.
- ✅ Randomized gene search: tier-weighted sampling for list-query variety.

---

*Last updated: 2026-04-28*
