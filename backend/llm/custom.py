"""Custom HTTP LLM client (OpenAI-compatible).

Useful for:
  - Self-hosted LLMs with OpenAI-compatible APIs (vLLM, llama.cpp server, etc.)
  - LLM proxies (OpenRouter, LiteLLM, OneAPI, etc.)
  - Private/internal LLM services
  - The MiniMax platform (api.minimaxi.com / api.minimax.io)

Contract:
  POST {base_url}/chat/completions
  Headers: Authorization: Bearer {api_key}   (if api_key provided)
  Body:    OpenAI chat completions JSON
  Resp:    OpenAI chat completions JSON
"""
from __future__ import annotations

import json
import re
from typing import Iterator, Optional

import httpx

from backend.llm.base import LLMClient, LLMResponse, Message, ToolCall
from backend.utils import LLMError, get_logger

log = get_logger(__name__)

# Strip <think>...</think> blocks emitted by reasoning models (MiniMax-M3,
# Qwen3, DeepSeek-R1, etc.). These get smuggled into content / tool args
# and confuse downstream parsers.
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


def _extract_think(text: str) -> tuple[str, str]:
    """Return (stripped_text, joined_thinking). Preserves order of multiple
    think blocks if present."""
    if not text:
        return text, ""
    parts = _THINK_RE.findall(text)
    if not parts:
        return text, ""
    thinking = "\n\n".join(p.strip() for p in parts if p.strip())
    stripped = _THINK_RE.sub("", text).strip()
    return stripped, thinking


def _strip_think(text: str) -> str:
    """Backwards-compat: just the stripped text."""
    return _extract_think(text)[0]


def _to_openai_messages(messages: list[Message]) -> list[dict]:
    out = []
    for m in messages:
        if m.role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id or "tool",
                    "content": m.content,
                }
            )
            continue
        msg: dict = {"role": m.role, "content": m.content}
        if m.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id or f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for i, tc in enumerate(m.tool_calls)
            ]
        out.append(msg)
    return out


def _from_openai_response(data: dict, model: str) -> LLMResponse:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    raw_content = msg.get("content", "") or ""
    content, content_thinking = _extract_think(raw_content)
    tcs: list[ToolCall] = []
    tool_thinking_parts: list[str] = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        raw_args = fn.get("arguments") or "{}"
        # Reasoning models sometimes leak <think>...</think> into the
        # function-arguments JSON. Strip it before parsing, but preserve it.
        cleaned_args, args_thinking = _extract_think(raw_args)
        if args_thinking:
            tool_thinking_parts.append(args_thinking)
        try:
            args = json.loads(cleaned_args or "{}")
        except Exception:
            args = {}
        tcs.append(ToolCall(name=fn.get("name", ""), arguments=args, id=tc.get("id", "")))
    # Also check reasoning_content field (some providers split this off)
    extra_thinking = msg.get("reasoning_content") or ""
    thinking_chunks = [c for c in [content_thinking, *tool_thinking_parts, extra_thinking] if c]
    thinking = "\n\n".join(thinking_chunks)
    return LLMResponse(
        content=content,
        tool_calls=tcs,
        model=data.get("model", model),
        usage=data.get("usage") or {},
        raw=data,
        thinking=thinking,
    )


class CustomClient(LLMClient):
    """OpenAI-compatible HTTP client for any custom endpoint."""

    provider = "custom"

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, **kwargs)
        if not base_url:
            raise LLMError(
                "Custom LLM requires base_url",
                hint="Set it in Settings → LLM → Custom / OpenAI-Compatible.",
                provider="custom",
            )
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self._client = httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def chat(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        payload: dict = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"

        try:
            r = self._client.post(url, json=payload, headers=self._headers())
            if r.status_code >= 400:
                raise LLMError(
                    f"Custom LLM HTTP {r.status_code}: {r.text[:300]}",
                    hint=f"Check {url} and your API key.",
                    provider="custom",
                )
            data = r.json()
        except httpx.HTTPError as e:
            raise LLMError(f"Custom LLM request failed: {e}", hint=f"Check {url}", provider="custom")
        except json.JSONDecodeError as e:
            raise LLMError(f"Custom LLM returned invalid JSON: {e}", provider="custom")

        return _from_openai_response(data, self.model)

    def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> Iterator[dict]:
        url = f"{self.base_url}/chat/completions"
        payload: dict = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        full_content: list[str] = []
        full_thinking: list[str] = []
        # Streaming state machine for separating <think>...</think> from
        # visible content. Buffer `<` and probe for <think> / </think>.
        in_think = False
        tag_buf = ""
        tag_text_buf: list[str] = []   # text inside current think block
        vis_buf: list[str] = []        # text outside (visible content)

        def _flush_text_buffer():
            """Push accumulated text from current mode (think or content)."""
            if not tag_text_buf and not vis_buf:
                return
            if in_think:
                if vis_buf:
                    full_content.append("".join(vis_buf))
                    yield {"type": "content", "text": "".join(vis_buf)}
                    vis_buf.clear()
            else:
                if tag_text_buf:
                    full_thinking.append("".join(tag_text_buf))
                    yield {"type": "think", "text": "".join(tag_text_buf)}
                    tag_text_buf.clear()

        try:
            with self._client.stream("POST", url, json=payload, headers=self._headers(), timeout=None) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload_str = line[6:].strip()
                    if payload_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload_str)
                        delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                        content = delta.get("content")
                        if not content:
                            continue
                        for ch in content:
                            tag_buf += ch
                            low = tag_buf.lower()
                            if in_think:
                                # Looking for closing </think>
                                if low.endswith("</think>"):
                                    # Extract content before </think>
                                    closing_idx = low.rfind("</think>")
                                    inner = tag_buf[:closing_idx]
                                    if inner:
                                        tag_text_buf.append(inner)
                                        full_thinking.append(inner)
                                        yield {"type": "think", "text": inner}
                                    in_think = False
                                    tag_buf = ""
                                    tag_text_buf = []
                                # else keep accumulating
                            else:
                                # Looking for opening <think>
                                if "<think>" in low:
                                    # Find exact position
                                    open_idx = low.find("<think>")
                                    # Text before the tag is visible content
                                    pre = tag_buf[:open_idx]
                                    if pre:
                                        vis_buf.append(pre)
                                        full_content.append(pre)
                                        yield {"type": "content", "text": pre}
                                    in_think = True
                                    tag_buf = ""
                                    tag_text_buf = []
                                else:
                                    # Need more chars to decide — keep buffering
                                    # until we have enough to know if it's a
                                    # <think> tag or just visible text.
                                    # We use a simple heuristic: if tag_buf
                                    # could be the start of "<" + any other char,
                                    # keep buffering. Once we see a char that
                                    # breaks <think>, flush as content.
                                    if len(tag_buf) >= 7 or (
                                        len(tag_buf) >= 2 and not "<t" in low
                                    ):
                                        # Not a <think> tag (any other tag, or
                                        # plain text that doesn't start with <t)
                                        vis_buf.append(tag_buf)
                                        full_content.append(tag_buf)
                                        yield {"type": "content", "text": tag_buf}
                                        tag_buf = ""
                    except json.JSONDecodeError:
                        continue
                # Flush anything left
                if tag_buf:
                    if in_think:
                        full_thinking.append(tag_buf)
                        yield {"type": "think", "text": tag_buf}
                    else:
                        full_content.append(tag_buf)
                        yield {"type": "content", "text": tag_buf}
        except httpx.HTTPError as e:
            raise LLMError(f"Custom LLM stream failed: {e}", provider="custom")

        yield {
            "type": "done",
            "content": "".join(full_content),
            "thinking": "".join(full_thinking),
        }

    def list_models(self) -> list[str]:
        try:
            r = self._client.get(f"{self.base_url}/models", headers=self._headers(), timeout=5.0)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data.get("data"), list):
                    return [m.get("id", "") for m in data["data"] if m.get("id")]
        except Exception as e:
            log.debug(f"list_models failed: {e}")
        return [self.model]

    def test_connectivity(self) -> dict:
        """Quick health probe: GET /models, return ok + first model or error."""
        try:
            r = self._client.get(f"{self.base_url}/models", headers=self._headers(), timeout=5.0)
            return {
                "ok": r.status_code == 200,
                "status_code": r.status_code,
                "url": f"{self.base_url}/models",
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "url": f"{self.base_url}/models"}
