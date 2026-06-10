"""OpenAI client (also works for any OpenAI-compatible endpoint)."""
from __future__ import annotations

import os
from typing import Iterator, Optional

from openai import OpenAI

from backend.llm.base import LLMClient, LLMResponse, Message, ToolCall
from backend.utils import LLMError, get_logger

log = get_logger(__name__)


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
                    "function": {"name": tc.name, "arguments": _json_dumps(tc.arguments)},
                }
                for i, tc in enumerate(m.tool_calls)
            ]
        out.append(msg)
    return out


def _json_dumps(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


def _from_openai_response(resp) -> LLMResponse:
    choice = resp.choices[0]
    msg = choice.message
    tcs = []
    for tc in msg.tool_calls or []:
        import json

        try:
            args = json.loads(tc.function.arguments or "{}")
        except Exception:
            args = {}
        tcs.append(ToolCall(name=tc.function.name, arguments=args, id=tc.id or ""))
    usage = {}
    if getattr(resp, "usage", None):
        usage = {
            "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0),
            "completion_tokens": getattr(resp.usage, "completion_tokens", 0),
            "total_tokens": getattr(resp.usage, "total_tokens", 0),
        }
    return LLMResponse(
        content=msg.content or "",
        tool_calls=tcs,
        model=resp.model,
        usage=usage,
        raw=resp,
    )


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model, **kwargs)
        api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise LLMError(
                "OPENAI_API_KEY is not set",
                hint="Set it in .env, your shell, or in Settings UI.",
                provider="openai",
            )
        self._client = OpenAI(api_key=api_key, base_url=base_url or None)

    def list_models(self) -> list[str]:
        try:
            return [m.id for m in self._client.models.list().data]
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
        kwargs: dict = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
            kwargs["tool_choice"] = "auto"
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            raise LLMError(f"OpenAI chat failed: {e}", provider="openai")
        return _from_openai_response(resp)

    def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> Iterator[dict]:
        kwargs: dict = {
            "model": self.model,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
        try:
            stream = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            raise LLMError(f"OpenAI stream failed: {e}", provider="openai")
        full: list[str] = []
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    full.append(delta.content)
                    yield {"type": "content", "text": delta.content}
            except (IndexError, AttributeError):
                continue
        yield {"type": "done", "content": "".join(full), "thinking": ""}
