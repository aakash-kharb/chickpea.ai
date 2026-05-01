# Development Guide

## Prerequisites

- Python 3.10+
- pip
- access to selected LLM backend:
  - Groq API key, or
  - local Ollama instance

## Install

```bash
cd rag_pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Test

Run full current test suite:

```bash
python -m pytest tests/test_agents.py -v
```

## Code Standards

Primary standards are documented in `rag_pipeline/rules.md`.

Key requirements:

- normalize IDs to canonical `Ca_XXXXX`
- no NaN imputation for expression values
- use pseudo-count Log2FC formula with +1
- route all LLM calls through `modules/llm_interface.py`
- avoid hardcoded absolute paths
- keep modules independently testable where possible

## Module Responsibilities

- `pipeline.py`: orchestration and CLI
- `modules/ai_router.py`: intent/scope routing and validation capsule
- `modules/semantic_router.py`: deterministic fallback routing
- `modules/id_mapper.py`: ID resolution and canonicalization
- `modules/gene_collector.py`: unified retrieval and report formatting
- `modules/gene_search_agent.py`: list-query filtering and ranking
- `modules/llm_interface.py`: backend abstraction

## Adding New Expression Datasets

1. Place new CSV in `Individual Files/`.
2. Add file metadata and column mappings to `_FILE_REGISTRY` in `modules/gene_collector.py`.
3. Include stress type, gene ID column hint, and control/stress column pairs.
4. Add tests that validate expected parsing and classification behavior.

## Adding New Intents or Output Formats

1. Update router prompt and output contract in `modules/ai_router.py`.
2. Ensure `pipeline.py` handles the new intent path.
3. Update validator checks to enforce required sections.
4. Add unit tests for router JSON and fallback behavior.

## Troubleshooting

### Import error: `groq` package not installed

```bash
pip install groq
```

### Missing API key

Set `GROQ_API_KEY` in `.env`.

### Ollama connection error

- verify Ollama is running
- verify `OLLAMA_BASE_URL`
- verify selected local model is installed

### Empty or missing expression evidence

- verify gene ID resolution in logs (`--verbose`)
- verify the gene exists in the relevant `Individual Files` datasets
- check for unresolved IDs in `mapping.csv`

## Project Completion

This documentation and implementation set is marked complete as of April 21, 2026.

Current completion checklist:

- Core pipeline architecture documented.
- Dataset contracts and interpretation rules documented.
- CLI behavior and configuration documented.
- Development and testing workflow documented.
- Project completion walkthrough documented.
