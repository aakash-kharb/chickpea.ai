"""
app.py — Chickpea SRG RAG GUI Backend
--------------------------------------
FastAPI server that wraps pipeline.py via SSE (Server-Sent Events).

Architecture:
  POST /api/query  → SSE stream
    • _GuiTracker  feeds stage events into an asyncio.Queue
    • run_pipeline  runs in asyncio.to_thread (non-blocking)
    • SSE generator drains the queue and yields events to the browser

Endpoints:
  GET  /api/health     → backend status + active LLM backend
  POST /api/query      → SSE stream of stage + result events
  GET  /               → serves frontend (production build in static/)
  GET  /* (static)     → frontend assets
"""

import asyncio
import json
import os
import sys
from collections import deque
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# ── Resolve paths ──────────────────────────────────────────────────────────────
_GUI_BACKEND  = Path(__file__).parent.resolve()
_CLI_ROOT     = _GUI_BACKEND.parent.parent / "rag_pipeline"

# Load the CLI's .env (contains GROQ_API_KEY, LLM_BACKEND, etc.)
load_dotenv(_CLI_ROOT / ".env")

# Inject CLI onto sys.path so we can import pipeline.py directly
sys.path.insert(0, str(_CLI_ROOT))

from pipeline import run_pipeline, get_active_backend, ConversationTurn  # type: ignore[import]

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(title="Chickpea SRG RAG GUI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Stage definitions (mirrors _StageTracker._STAGES in pipeline.py) ──────────
STAGES: list[tuple[str, str]] = [
    ("routing",    "Semantic & intent interpretation"),
    ("resolving",  "Resolving gene identifiers"),
    ("retrieving", "Data retrieval & packet assembly"),
    ("analysing",  "Agents running  ·  LLM synthesis"),
    ("validating", "Routing capsule  ·  output validation"),
    ("rendering",  "Composing final response"),
]
STAGE_MAP: dict[str, int] = {k: i for i, (k, _) in enumerate(STAGES)}

# ── Server-side conversation history (mirrors CLI _conversation_history) ──────
_conversation_history: deque = deque(maxlen=3)


# ── _GuiTracker — mirrors pipeline._StageTracker interface ──────────────────
class _GuiTracker:
    """
    Drop-in replacement for pipeline._StageTracker.
    Instead of animating a rich.live panel, it puts SSE-ready dicts
    into an asyncio.Queue for the /api/query generator to drain.

    The Queue is created on the event loop that owns the SSE generator.
    run_pipeline() runs in a thread (asyncio.to_thread), so we use
    loop.call_soon_threadsafe to enqueue from the worker thread.
    """

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self._queue = queue
        self._loop  = loop

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def advance(self, stage_key: str) -> None:
        idx = STAGE_MAP.get(stage_key, -1)
        if idx < 0:
            return
        label = STAGES[idx][1]
        payload = json.dumps({"stage": stage_key, "label": label, "index": idx})
        # Thread-safe enqueue from the worker thread
        self._loop.call_soon_threadsafe(self._queue.put_nowait, ("stage", payload))

    def finish(self) -> None:
        """Signal the SSE generator that the pipeline is done."""
        self._loop.call_soon_threadsafe(self._queue.put_nowait, ("__done__", ""))


# ── Request / response models ──────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    gene_id: str | None = None
    verbose: bool = False


# ── /api/health ───────────────────────────────────────────────────────────────
@app.get("/api/health")
def health() -> dict:
    try:
        backend = get_active_backend()
    except Exception as exc:
        backend = f"error: {exc}"
    return {"status": "ok", "backend": backend}


# ── /api/query — SSE stream ───────────────────────────────────────────────────
@app.post("/api/query")
async def query_pipeline(req: QueryRequest, request: Request) -> EventSourceResponse:
    """
    Stream pipeline execution as Server-Sent Events.

    Events emitted:
      stage   — one per pipeline stage (6 total)
      result  — final PipelineResult dict (llm_response, intent, metadata)
      error   — if run_pipeline() raises or returns an error key
    """
    return EventSourceResponse(_stream(req, request), ping=15)


async def _stream(req: QueryRequest, request: Request) -> AsyncGenerator:
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()
    tracker = _GuiTracker(queue, loop)

    async def _run_in_thread() -> None:
        """Execute pipeline in a thread, then enqueue completion signal."""
        try:
            result = await asyncio.to_thread(
                run_pipeline,
                req.query,
                req.gene_id,
                req.verbose,
                tracker,
                list(_conversation_history),
            )
            tracker.advance("rendering")

            # ── Push to conversation history ──────────────────────────
            if "error" not in result:
                resp_text = result.get("llm_response", "")
                summary = resp_text[:300].rsplit(" ", 1)[0] if len(resp_text) > 300 else resp_text
                gene_id_str = result.get("gene_id", "")
                _conversation_history.append(ConversationTurn(
                    query=req.query,
                    gene_ids=(
                        [g.strip() for g in gene_id_str.split(",")]
                        if gene_id_str and gene_id_str != "[gene list query]"
                        else []
                    ),
                    intent=result.get("intent", ""),
                    response_summary=summary,
                    routing_capsule=result.get("routing_capsule", ""),
                ))

            payload = {
                "gene_id":           result.get("gene_id", ""),
                "intent":            result.get("intent", ""),
                "output_format":     result.get("output_format", ""),
                "agents_used":       result.get("agents_used", []),
                "llm_response":      result.get("llm_response", ""),
                "validation_applied":result.get("validation_applied", False),
                "router_note":       result.get("router_note", ""),
                "error":             result.get("error"),
            }
            loop.call_soon_threadsafe(queue.put_nowait, ("result", json.dumps(payload)))
        except Exception as exc:
            err = json.dumps({"message": str(exc)})
            loop.call_soon_threadsafe(queue.put_nowait, ("error", err))
        finally:
            tracker.finish()

    # Fire pipeline in background
    asyncio.create_task(_run_in_thread())

    # Drain the queue and yield SSE events
    while True:
        if await request.is_disconnected():
            break

        try:
            event_type, data = await asyncio.wait_for(queue.get(), timeout=180.0)
        except asyncio.TimeoutError:
            yield {"event": "error", "data": json.dumps({"message": "Pipeline timed out."})}
            break

        if event_type == "__done__":
            break

        yield {"event": event_type, "data": data}

        if event_type in ("result", "error"):
            # Drain the done signal so the queue doesn't leak
            try:
                await asyncio.wait_for(queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            break


# ── Static files (production build) ───────────────────────────────────────────
_STATIC_DIR = _GUI_BACKEND / "static"

if _STATIC_DIR.exists():
    # Mount assets (JS, CSS) — exclude index.html which needs SPA fallback
    app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    def serve_root() -> FileResponse:
        return FileResponse(str(_STATIC_DIR / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        """SPA fallback — serve index.html for all non-API routes."""
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        file = _STATIC_DIR / full_path
        if file.exists() and file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(_STATIC_DIR / "index.html"))


# ── Dev entry ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=True)
