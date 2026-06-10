"""LLM availability detection on startup.

Returns a tuple of (provider, model) or (None, None) when nothing is reachable.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from backend.config import get_settings
from backend.utils import get_logger

log = get_logger(__name__)


def probe_ollama(base_url: str, timeout: float = 2.0) -> Optional[str]:
    """Return the first available Ollama model, or None."""
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            if models:
                return models[0]
    except Exception as e:
        log.debug(f"Ollama probe failed: {e}")
    return None


def detect_default_llm() -> tuple[Optional[str], Optional[str]]:
    """Return (provider, model) of the first available LLM, or (None, None)."""
    s = get_settings()
    base = os.getenv("OLLAMA_HOST") or s.llm.providers.ollama.base_url
    m = probe_ollama(base)
    if m:
        return "ollama", m
    if os.getenv("OPENAI_API_KEY"):
        return "openai", s.llm.providers.openai.default_model
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic", s.llm.providers.anthropic.default_model
    # Custom / OpenAI-compatible: any of URL or key set is enough
    custom_url = os.getenv("CUSTOM_LLM_URL") or s.llm.providers.custom.base_url
    custom_key = os.getenv("CUSTOM_LLM_API_KEY") or s.llm.providers.custom.api_key
    if custom_url and custom_key:
        return "custom", s.llm.providers.custom.default_model or "custom-model"
    return None, None
