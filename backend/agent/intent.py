"""Intent classification via LLM (function-calling or fallback JSON parse)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from backend.llm.base import LLMClient, Message
from backend.utils import AgentError, get_logger

log = get_logger(__name__)


@dataclass
class IntentResult:
    intent: str
    confidence: float
    params: dict
    reasoning: str = ""
    thinking: str = ""  # extracted from <think>...</think> if reasoning model


INTENT_TOOLS = [
    {
        "name": "classify_intent",
        "description": "Classify the user's intent and extract parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": ["query_data", "generate_chart", "generate_script", "explain_data"],
                },
                "confidence": {"type": "number"},
                "params": {
                    "type": "object",
                    "description": "Free-form parameters relevant to the intent (metric, dimension, time_range, chart_type, script_subtype, etc.)",
                },
                "reasoning": {"type": "string"},
            },
            "required": ["intent", "confidence", "params"],
        },
    }
]


def _parse_json_block(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from LLM output."""
    if not text:
        return None
    # try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # try ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # try first {...} block
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def classify_intent(llm: LLMClient, question: str, *, system_prompt: str) -> IntentResult:
    """Classify user intent via the LLM."""
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=question),
    ]
    try:
        resp = llm.chat(messages, tools=INTENT_TOOLS, temperature=0.0)
    except Exception as e:
        log.warning(f"Function-calling intent failed, falling back to JSON: {e}")
        resp = llm.chat(messages, temperature=0.0)

    payload: Optional[dict] = None
    if resp.has_tool_calls:
        tc = resp.get_tool("classify_intent")
        if tc and tc.arguments:
            payload = tc.arguments
    if payload is None:
        payload = _parse_json_block(resp.content)

    if not payload or "intent" not in payload:
        # Heuristic fallback
        q = question.lower()
        if any(kw in q for kw in ["存储过程", "procedure", "sp "]):
            intent = "generate_script"
        elif any(kw in q for kw in ["图", "chart", "画", "可视化"]):
            intent = "generate_chart"
        elif any(kw in q for kw in ["解释", "explain", "说明"]):
            intent = "explain_data"
        else:
            intent = "query_data"
        return IntentResult(intent=intent, confidence=0.5, params={}, reasoning="heuristic fallback")

    return IntentResult(
        intent=str(payload.get("intent", "query_data")),
        confidence=float(payload.get("confidence", 0.8) or 0.8),
        params=dict(payload.get("params", {}) or {}),
        reasoning=str(payload.get("reasoning", "") or ""),
        thinking=resp.thinking or "",
    )


def classify_intent_stream(llm: LLMClient, question: str, *, system_prompt: str):
    """Streaming variant. Yields (event_dict, None) for each LLM chunk,
    then finally yields (None, IntentResult)."""
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=question),
    ]
    full_content: list[str] = []
    full_thinking: list[str] = []
    tool_args_buf: list[str] = []
    tool_name: Optional[str] = None
    try:
        # Try streaming with tools; if it fails, fall back to non-streaming
        for ev in llm.chat_stream(messages, tools=INTENT_TOOLS, temperature=0.0):
            t = ev.get("type")
            if t == "think":
                full_thinking.append(ev.get("text", ""))
                yield ev, None
            elif t == "content":
                full_content.append(ev.get("text", ""))
                yield ev, None
            elif t == "tool_call":
                tool_name = ev.get("name")
                tool_args_buf.append(ev.get("arguments", ""))
            elif t == "done":
                if not ev.get("content") and not full_content:
                    # Fallback to non-streaming
                    resp = llm.chat(messages, tools=INTENT_TOOLS, temperature=0.0)
                    full_content.append(resp.content)
                    full_thinking.append(resp.thinking or "")
                    if resp.has_tool_calls:
                        tc = resp.get_tool("classify_intent")
                        if tc and tc.arguments:
                            tool_name = tc.name
                            import json as _json
                            tool_args_buf.append(_json.dumps(tc.arguments, ensure_ascii=False))
    except Exception as e:
        log.warning(f"Streaming intent failed, falling back to non-stream: {e}")
        resp = llm.chat(messages, tools=INTENT_TOOLS, temperature=0.0)
        full_content.append(resp.content)
        full_thinking.append(resp.thinking or "")

    content = "".join(full_content)
    thinking = "".join(full_thinking)

    payload: Optional[dict] = None
    if tool_name and tool_args_buf:
        try:
            import json as _json
            payload = _json.loads("".join(tool_args_buf))
        except Exception:
            payload = None
    if payload is None:
        payload = _parse_json_block(content)

    if not payload or "intent" not in payload:
        q = question.lower()
        if any(kw in q for kw in ["存储过程", "procedure", "sp "]):
            intent = "generate_script"
        elif any(kw in q for kw in ["图", "chart", "画", "可视化"]):
            intent = "generate_chart"
        elif any(kw in q for kw in ["解释", "explain", "说明"]):
            intent = "explain_data"
        else:
            intent = "query_data"
        result = IntentResult(intent=intent, confidence=0.5, params={}, reasoning="heuristic fallback", thinking=thinking)
    else:
        result = IntentResult(
            intent=str(payload.get("intent", "query_data")),
            confidence=float(payload.get("confidence", 0.8) or 0.8),
            params=dict(payload.get("params", {}) or {}),
            reasoning=str(payload.get("reasoning", "") or ""),
            thinking=thinking,
        )
    yield {"type": "done"}, result
