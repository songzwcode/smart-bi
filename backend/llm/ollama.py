"""Ollama HTTP client.

Communicates with a local Ollama daemon (default: http://localhost:11434).
"""
from __future__ import annotations

import json
from typing import Iterator, Optional

import httpx

from backend.llm.base import LLMClient, LLMResponse, Message, ToolCall
from backend.utils import LLMError, get_logger

log = get_logger(__name__)


def _to_ollama_messages(messages: list[Message]) -> list[dict]:
    out = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "content": m.content})
            continue
        msg: dict = {"role": m.role, "content": m.content}
        if m.tool_calls:
            msg["tool_calls"] = [
                {
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                }
                for tc in m.tool_calls
            ]
        out.append(msg)
    return out


class OllamaClient(LLMClient):
    provider = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", **kwargs):
        super().__init__(model, **kwargs)
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0))

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        try:
            r = self._client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama request failed: {e}", hint=f"Check {url}", provider="ollama")

    def _stream(self, path: str, payload: dict) -> Iterator[dict]:
        url = f"{self.base_url}{path}"
        try:
            with self._client.stream("POST", url, json=payload, timeout=None) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama stream failed: {e}", provider="ollama")

    def list_models(self) -> list[str]:
        try:
            r = self._client.get(f"{self.base_url}/api/tags", timeout=5.0)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except Exception as e:
            log.debug(f"list_models failed: {e}")
            return [self.model]

    def chat(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": _to_ollama_messages(messages),
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        if tools:
            payload["tools"] = tools
        data = self._post("/api/chat", payload)
        msg = data.get("message", {}) or {}
        content = msg.get("content", "") or ""
        tcs = []
        for tc in msg.get("tool_calls", []) or []:
            fn = (tc or {}).get("function", {}) or {}
            tcs.append(
                ToolCall(
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", {}) or {},
                )
            )
        return LLMResponse(
            content=content,
            tool_calls=tcs,
            model=data.get("model", self.model),
            usage={},
            raw=data,
        )

    def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> Iterator[dict]:
        payload: dict = {
            "model": self.model,
            "messages": _to_ollama_messages(messages),
            "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        if tools:
            payload["tools"] = tools
        full: list[str] = []
        for chunk in self._stream("/api/chat", payload):
            chunk_msg = chunk.get("message", {}) or {}
            delta = chunk_msg.get("content", "")
            if delta:
                full.append(delta)
                yield {"type": "content", "text": delta}
            if chunk.get("done"):
                break
        yield {"type": "done", "content": "".join(full), "thinking": ""}
