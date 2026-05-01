# Chickpea Stress-Responsive Genes (SRG) RAG Pipeline

A Chickpea (Cicer arietinum) stress-responsive genes analysis system with:

- curated transcriptomics datasets (15 experiments, 4 abiotic stresses)
- a modular RAG pipeline (`rag_pipeline/`) with three-AI architecture
- a web GUI (`gui/`) with real-time streaming and interactive visualizations
- command-line workflows for gene profiles, expression checks, and gene-list discovery

## Repository at a glance

This repository combines raw/processed data assets, an executable Python pipeline, and a web interface.

**Data assets (project root):**

- `Stress_Binary_Matrix.csv` (1,630 genes): binary stress responsiveness labels
- `Ca_Peptide_Sequences.csv` (28,269 sequences): peptide sequences per `Ca_ID`
- `BiochemicalProperties.csv` (28,269 entries): pre-computed MW, pI, GRAVY, instability index, aliphatic index, atomic composition
- `mapping.csv` (27,078 mappings): canonical ID mapping (`Transcript id` <-> `LOC id`)
- `Individual Files/` (15 CSV files): stress experiment expression matrices

**Source code:**

- `rag_pipeline/`: routing, retrieval, analysis, and validation modules
- `gui/`: FastAPI backend + Vite/TypeScript frontend

## Core features

- Three-AI architecture: Router (scope/intent) → Analyst (biological analysis) → Validator (quality enforcement)
- Unified gene retrieval (`gene_collector`) for expression, sequence, stress labels, and biochemical properties
- Robust ID normalization (`Ca_XXXXX`, `LOC...`, gene symbols)
- Three-state stress interpretation: `RESPONSIVE`, `NOT_RESPONSIVE`, `UNKNOWN`
- Scope-aware AI router (rejects non-genomics queries)
- GEO/BioProject data provenance per stress experiment
- SVG diverging bar chart visualizations for Log2FC expression data
- Biochemical protein property profiling (MW, pI, GRAVY, instability, atomic composition)
- Randomized tier-weighted gene discovery for list queries
- Interactive GUI with frosted-glass design, real-time stage progress, and chat history

## Project structure

```text
Chickpea-SRG-RAG-Pipeline-GUI/
├── Ca_Peptide_Sequences.csv
├── BiochemicalProperties.csv
├── mapping.csv
├── Stress_Binary_Matrix.csv
├── Individual Files/               # 15 expression experiment CSVs
├── rag_pipeline/
│   ├── pipeline.py                 # Main orchestrator + CLI entrypoint
│   ├── requirements.txt
│   ├── rules.md
│   ├── knowledge/
│   │   └── chickpea_knowledge.md
│   ├── modules/
│   │   ├── ai_router.py            # Intent/scope routing + capsule
│   │   ├── gene_collector.py       # Unified data retrieval + formatting
│   │   ├── gene_search_agent.py    # List-query filtering + randomized sampling
│   │   ├── id_mapper.py            # ID resolution
│   │   ├── llm_interface.py        # Groq/Ollama abstraction
│   │   ├── biochem_properties.py   # Biochemical property CSV lookup
│   │   └── semantic_router.py      # Deterministic fallback router
│   └── tests/
│       └── test_agents.py
├── gui/
│   ├── run.sh                      # One-command dev launcher
│   ├── backend/
│   │   └── app.py                  # FastAPI SSE bridge
│   └── frontend/
│       └── src/
│           ├── main.ts             # App entry + event orchestration
│           ├── renderer.ts         # Markdown → DOM (tables, gene IDs, GEO links)
│           ├── heatmap.ts          # SVG diverging bar chart generator
│           ├── stages.ts           # Real-time stage progress panel
│           ├── api.ts              # SSE client
│           ├── genepicker.ts       # Gene ID / example popup
│           ├── types.ts            # Shared interfaces
│           └── style.css           # Full design system
├── docs/                           # Full project documentation
└── Developer Notes/                # Internal decisions + info reference
```

## Quick start — CLI

### 1) Create and activate a virtual environment

```bash
cd rag_pipeline
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment

Create `rag_pipeline/.env`:

```env
LLM_BACKEND=groq
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_ROUTER_MODEL=llama-3.1-8b-instant
```

### 4) Run the pipeline

```bash
python pipeline.py
```

## Quick start — GUI

```bash
cd gui
bash run.sh
# Backend  → http://localhost:7860
# Frontend → http://localhost:5173
```

## CLI usage

Run from `rag_pipeline/`.

```bash
python pipeline.py --query "Is Ca_00011 upregulated under salinity?"
python pipeline.py --query "Give me 5 drought responsive genes"
python pipeline.py --gene LOC101511858 --verbose
python pipeline.py --gene ARF1 --verbose --show-raw
python pipeline.py --query "Compare Ca_00001 and Ca_00999 under heat" --json
```

## Testing

```bash
python -m pytest tests/test_agents.py -v
```

## Documentation index

- [Documentation Home](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Datasets](docs/DATASETS.md)
- [CLI Reference](docs/CLI_REFERENCE.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Project Completion Walkthrough](docs/PROJECT_COMPLETION_WALKTHROUGH.md)

## Notes

- The pipeline is specialized for chickpea stress-responsive genes transcriptomics queries.
- Out-of-scope questions are intentionally rejected by the AI router.
- LLM calls are abstracted through `modules/llm_interface.py`.
- No wet-lab experiments are involved — this is a purely computational analysis tool.
