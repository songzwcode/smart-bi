"""LLM client base + response types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional, Union

# Stream event types emitted by chat_stream():
#   {"type": "think",   "text": "..."}   — reasoning chunk (inside <think>...</think>)
#   {"type": "content", "text": "..."}   — visible answer chunk
#   {"type": "tool_call", "name": "...", "arguments": "..."}  — tool call (when supported)
#   {"type": "done",    "content": "...", "thinking": "..."}  — final accumulator
StreamEvent = dict


@dataclass
class ToolCall:
    """A single tool/function call returned by the LLM."""
    name: str
    arguments: dict = field(default_factory=dict)
    id: str = ""


@dataclass
class LLMResponse:
    """Unified LLM response."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)
    raw: Any = None
    # Reasoning-model content extracted from <think>...</think> blocks
    # (MiniMax-M3, Qwen3, DeepSeek-R1, etc.). Preserved for UI display
    # even though it's stripped from `content` for downstream parsing.
    thinking: str = ""

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def get_tool(self, name: str) -> Optional[ToolCall]:
        for t in self.tool_calls:
            if t.name == name:
                return t
        return None


@dataclass
class Message:
    role: str   # system | user | assistant | tool
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""   # for role=tool
    name: str = ""           # for role=tool


class LLMClient(ABC):
    """Abstract LLM client.

    Concrete subclasses: OllamaClient, OpenAIClient, AnthropicClient.
    """

    provider: str = "abstract"

    def __init__(self, model: str, **kwargs: Any):
        self.model = model
        self.kwargs = kwargs

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """One-shot chat. Returns full LLMResponse."""

    def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> Iterator[StreamEvent]:
        """Streaming variant. Default: falls back to non-streaming.

        Yields StreamEvent dicts:
          - {"type": "think", "text": "..."}    — reasoning chunk
          - {"type": "content", "text": "..."}  — visible answer chunk
          - {"type": "done", "content": "...", "thinking": "..."} — final

        Subclasses should override for true token-by-token streaming.
        """
        resp = self.chat(messages, tools=tools, temperature=temperature, max_tokens=max_tokens)
        if resp.thinking:
            yield {"type": "think", "text": resp.thinking}
        if resp.content:
            yield {"type": "content", "text": resp.content}
        yield {"type": "done", "content": resp.content, "thinking": resp.thinking}

    def list_models(self) -> list[str]:
        """List available models. Subclasses override for live listing."""
        return [self.model]
