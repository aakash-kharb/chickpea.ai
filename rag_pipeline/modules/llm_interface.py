"""
llm_interface.py
----------------
Unified LLM backend abstraction layer.

Supports:
  - Groq API (default)
  - Ollama (local, swap-ready)

Usage:
    from modules.llm_interface import get_llm_response
    reply = get_llm_response(system_prompt, user_prompt)

To switch backends set LLM_BACKEND=ollama in .env.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Backend selection ──────────────────────────────────────────────────────────
_BACKEND          = os.getenv("LLM_BACKEND", "groq").lower()
_GROQ_MODEL       = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# Cheaper/faster model for lightweight tasks (routing, validation).  Set in .env:
# GROQ_ROUTER_MODEL=llama-3.1-8b-instant
_GROQ_ROUTER_MODEL = os.getenv("GROQ_ROUTER_MODEL", _GROQ_MODEL)
_OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL", "llama3")
_OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


# ── Groq backend ──────────────────────────────────────────────────────────────
def _call_groq(system_prompt: str, user_prompt: str, model: str = None) -> str:
    """Send a chat completion request to Groq API."""
    try:
        from groq import Groq  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "groq package not installed. Run: pip install groq"
        ) from exc

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY is not set. Add it to your .env file."
        )

    chosen_model = model or _GROQ_MODEL
    client = Groq(api_key=api_key)
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=chosen_model,
        temperature=0.2,        # lower temperature → more deterministic / factual
        max_tokens=4096,
    )
    return chat_completion.choices[0].message.content.strip()


# ── Ollama backend ─────────────────────────────────────────────────────────────
def _call_ollama(system_prompt: str, user_prompt: str) -> str:
    """Send a chat request to a local Ollama instance."""
    url = f"{_OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise ConnectionError(
            f"Cannot reach Ollama at {_OLLAMA_BASE_URL}. Is it running?"
        ) from exc

    data = response.json()
    return data["message"]["content"].strip()


# ── Public interface ───────────────────────────────────────────────────────────
def get_llm_response(system_prompt: str, user_prompt: str) -> str:
    """
    Route the request to the configured LLM backend.

    Parameters
    ----------
    system_prompt : str
        The system-level instruction grounding the LLM in domain context.
    user_prompt : str
        The assembled user query + retrieved context.

    Returns
    -------
    str
        Raw text response from the LLM.
    """
    if _BACKEND == "groq":
        return _call_groq(system_prompt, user_prompt)
    elif _BACKEND == "ollama":
        return _call_ollama(system_prompt, user_prompt)
    else:
        raise ValueError(
            f"Unknown LLM_BACKEND='{_BACKEND}'. Choose 'groq' or 'ollama'."
        )


def get_llm_response_with_model(system_prompt: str, user_prompt: str, model: str) -> str:
    """
    Like get_llm_response() but allows overriding the model for a single call.
    Useful for using a smaller/faster model for routing or validation tasks.

    With Groq this uses the specified model directly.
    With Ollama the model override is not supported — falls back to default.
    """
    if _BACKEND == "groq":
        return _call_groq(system_prompt, user_prompt, model=model)
    return _call_ollama(system_prompt, user_prompt)


def get_router_model_name() -> str:
    """Return the model name used for routing calls."""
    return _GROQ_ROUTER_MODEL


def get_active_backend() -> str:
    """Return a human-readable description of the active backend."""
    if _BACKEND == "groq":
        router_note = (
            f" (router: {_GROQ_ROUTER_MODEL})"
            if _GROQ_ROUTER_MODEL != _GROQ_MODEL else ""
        )
        return f"Groq API | model={_GROQ_MODEL}{router_note}"
    return f"Ollama local | model={_OLLAMA_MODEL} | url={_OLLAMA_BASE_URL}"
