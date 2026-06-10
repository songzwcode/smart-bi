"""Anthropic Claude client."""
from __future__ import annotations

import os
from typing import Iterator, Optional

from anthropic import Anthropic

from backend.llm.base import LLMClient, LLMResponse, Message, ToolCall
from backend.utils import LLMError, get_logger

log = get_logger(__name__)


def _to_anthropic_messages(messages: list[Message]) -> tuple[Optional[str], list[dict]]:
    """Anthropic separates the system message from the rest."""
    system = None
    out = []
    for m in messages:
        if m.role == "system":
            system = (system or "") + ("\n" if system else "") + m.content
            continue
        if m.role == "tool":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id or "tool",
                            "content": m.content,
                        }
                    ],
                }
            )
            continue
        if m.role == "assistant":
            content_blocks = []
            if m.content:
                content_blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.id or f"toolu_{id(tc)}",
                        "name": tc.name,
                        "input": tc.arguments,
                    }
                )
            out.append({"role": "assistant", "content": content_blocks or [{"type": "text", "text": ""}]})
        else:
            out.append({"role": m.role, "content": m.content})
    return system, out


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set",
                hint="Set it in .env, your shell, or in Settings UI.",
                provider="anthropic",
            )
        self._client = Anthropic(api_key=api_key)

    def list_models(self) -> list[str]:
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ]

    def chat(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        system, msgs = _to_anthropic_messages(messages)
        kwargs: dict = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": max_tokens or 2048,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]
        try:
            resp = self._client.messages.create(**kwargs)
        except Exception as e:
            raise LLMError(f"Anthropic chat failed: {e}", provider="anthropic")

        text_parts: list[str] = []
        tcs: list[ToolCall] = []
        for block in resp.content or []:
            if getattr(block, "type", "") == "text":
                text_parts.append(block.text)
            elif getattr(block, "type", "") == "tool_use":
                tcs.append(
                    ToolCall(
                        name=block.name,
                        arguments=block.input or {},
                        id=block.id,
                    )
                )
        usage = {}
        if getattr(resp, "usage", None):
            usage = {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            }
        return LLMResponse(
            content="".join(text_parts),
            tool_calls=tcs,
            model=resp.model,
            usage=usage,
            raw=resp,
        )

    def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> Iterator[dict]:
        system, msgs = _to_anthropic_messages(messages)
        kwargs: dict = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": max_tokens or 2048,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]
        full: list[str] = []
        try:
            with self._client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    full.append(text)
                    yield {"type": "content", "text": text}
        except Exception as e:
            raise LLMError(f"Anthropic stream failed: {e}", provider="anthropic")
        yield {"type": "done", "content": "".join(full), "thinking": ""}
