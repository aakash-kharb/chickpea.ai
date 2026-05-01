# CLI Reference

All commands below are run from `rag_pipeline/`.

For the full documentation map, see `README.md` in this `docs/` folder.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in `rag_pipeline/`:

```env
LLM_BACKEND=groq
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_ROUTER_MODEL=llama-3.1-8b-instant

# Optional Ollama settings
# LLM_BACKEND=ollama
# OLLAMA_MODEL=llama3
# OLLAMA_BASE_URL=http://localhost:11434
```

## Main Command

```bash
python pipeline.py [OPTIONS]
```

### Options

- `--query`, `-q` `TEXT`: natural-language query
- `--gene`, `-g` `ID`: explicit gene identifier override
- `--verbose`, `-v`: print routing + context diagnostics
- `--json`: emit final response payload as JSON
- `--show-raw`: include pre-validation analysis output

## Usage Patterns

### Interactive mode

```bash
python pipeline.py
```

Starts a REPL-like prompt:

- `Query> ...`
- `exit`, `quit`, or `q` to stop

### Single gene profile

```bash
python pipeline.py --gene Ca_00011 --verbose
```

### LOC/symbol resolution

```bash
python pipeline.py --gene LOC101511858 --verbose
python pipeline.py --gene ARF1 --verbose
```

### Expression-focused query

```bash
python pipeline.py --query "Is Ca_00001 upregulated under salinity?"
```

### Gene list query

```bash
python pipeline.py --query "Give me 5 drought responsive genes"
```

### Multi-gene query

```bash
python pipeline.py --query "Compare Ca_00001 and Ca_00999 under heat"
```

### Machine-readable output

```bash
python pipeline.py --query "Is Ca_00011 upregulated under heat?" --json
```

## Output Contract

The pipeline returns a dictionary with fields including:

- `gene_id`
- `intent`
- `output_format`
- `agents_used`
- `llm_response`
- `llm_raw_response`
- `validation_applied`
- `router_note`
- `routing_capsule`

`--json` mode excludes large internal fields (`context`, raw verbose sections) before printing.

## Scope Behavior

Out-of-scope queries (math/general coding/general trivia) are declined with a specialized response. This behavior is intentional and configured in `modules/ai_router.py`.
