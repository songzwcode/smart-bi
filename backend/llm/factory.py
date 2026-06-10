"""LLM client factory + discovery."""
from __future__ import annotations

import os
from typing import Optional

import httpx

from backend.config import get_settings
from backend.llm.base import LLMClient
from backend.utils import LLMError, get_logger

log = get_logger(__name__)


def create_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    *,
    ollama_url: Optional[str] = None,
    custom_url: Optional[str] = None,
    custom_api_key: Optional[str] = None,
) -> LLMClient:
    """Create an LLM client based on settings + overrides."""
    s = get_settings()
    provider = (provider or s.llm.default_provider).lower()

    if provider == "ollama":
        from backend.llm.ollama import OllamaClient

        return OllamaClient(
            model=model or s.llm.providers.ollama.default_model,
            base_url=ollama_url or os.getenv("OLLAMA_HOST") or s.llm.providers.ollama.base_url,
        )

    if provider == "openai":
        from backend.llm.openai_client import OpenAIClient

        return OpenAIClient(
            model=model or s.llm.providers.openai.default_model,
            base_url=s.llm.providers.openai.base_url,
        )

    if provider in ("anthropic", "claude"):
        from backend.llm.anthropic import AnthropicClient

        return AnthropicClient(model=model or s.llm.providers.anthropic.default_model)

    if provider == "custom":
        from backend.llm.custom import CustomClient

        return CustomClient(
            model=model or s.llm.providers.custom.default_model,
            base_url=custom_url or os.getenv("CUSTOM_LLM_URL") or s.llm.providers.custom.base_url,
            api_key=custom_api_key or os.getenv("CUSTOM_LLM_API_KEY") or s.llm.providers.custom.api_key,
        )

    raise LLMError(f"Unknown provider: {provider}")


def list_available_llms() -> list[dict]:
    """Probe each provider and report what's available right now."""
    s = get_settings()
    out: list[dict] = []

    # Ollama
    base = os.getenv("OLLAMA_HOST") or s.llm.providers.ollama.base_url
    try:
        r = httpx.get(f"{base.rstrip('/')}/api/tags", timeout=2.0)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            out.append({"provider": "ollama", "available": True, "base_url": base, "models": models})
        else:
            out.append({"provider": "ollama", "available": False, "base_url": base, "error": f"HTTP {r.status_code}"})
    except Exception as e:
        out.append({"provider": "ollama", "available": False, "base_url": base, "error": str(e)})

    # OpenAI
    if os.getenv("OPENAI_API_KEY"):
        out.append({"provider": "openai", "available": True, "base_url": s.llm.providers.openai.base_url, "models": [s.llm.providers.openai.default_model]})
    else:
        out.append({"provider": "openai", "available": False, "error": "OPENAI_API_KEY not set"})

    # Anthropic
    if os.getenv("ANTHROPIC_API_KEY"):
        out.append({"provider": "anthropic", "available": True, "models": [s.llm.providers.anthropic.default_model]})
    else:
        out.append({"provider": "anthropic", "available": False, "error": "ANTHROPIC_API_KEY not set"})

    # Custom / OpenAI-compatible
    custom_url = os.getenv("CUSTOM_LLM_URL") or s.llm.providers.custom.base_url
    custom_key = os.getenv("CUSTOM_LLM_API_KEY") or s.llm.providers.custom.api_key
    if custom_url:
        out.append({
            "provider": "custom",
            "available": bool(custom_key),
            "base_url": custom_url,
            "models": [s.llm.providers.custom.default_model] if s.llm.providers.custom.default_model else [],
            "error": None if custom_key else "CUSTOM_LLM_API_KEY not set",
        })
    else:
        out.append({"provider": "custom", "available": False, "error": "base_url not configured"})

    return out
