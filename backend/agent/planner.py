"""Plan-and-Execute task decomposition."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from backend.llm.base import LLMClient, Message
from backend.utils import AgentError, get_logger

log = get_logger(__name__)


@dataclass
class PlanStep:
    id: int
    description: str
    action: str = "nl2sql"   # nl2sql | transform | compute
    depends_on: list[int] = field(default_factory=list)


@dataclass
class Plan:
    is_multi_step: bool
    steps: list[PlanStep] = field(default_factory=list)
    thinking: str = ""  # reasoning-model thinking from the planner LLM call

    def to_dict(self) -> dict:
        return {
            "is_multi_step": self.is_multi_step,
            "steps": [s.__dict__ for s in self.steps],
            "thinking": self.thinking,
        }


def _parse_json(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def make_plan(
    llm: LLMClient,
    question: str,
    *,
    system_prompt: str,
    max_steps: int = 6,
) -> Plan:
    """Ask the LLM to produce a step plan. Falls back to single-step."""
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=question),
    ]
    try:
        resp = llm.chat(messages, temperature=0.0)
    except Exception as e:
        log.warning(f"Planner LLM call failed: {e}")
        return Plan(is_multi_step=False, steps=[])

    data = _parse_json(resp.content)
    if not data:
        return Plan(is_multi_step=False, steps=[], thinking=resp.thinking or "")

    try:
        is_multi = bool(data.get("is_multi_step", False))
        steps_raw = data.get("steps", []) or []
        steps = [
            PlanStep(
                id=int(s.get("id", idx + 1)),
                description=str(s.get("description", "")),
                action=str(s.get("action", "nl2sql")),
                depends_on=list(s.get("depends_on", []) or []),
            )
            for idx, s in enumerate(steps_raw[:max_steps])
        ]
        return Plan(is_multi_step=is_multi, steps=steps, thinking=resp.thinking or "")
    except Exception as e:
        log.warning(f"Failed to parse plan: {e}")
        return Plan(is_multi_step=False, steps=[], thinking=resp.thinking or "")


def make_plan_stream(llm: LLMClient, question: str, *, system_prompt: str, max_steps: int = 6):
    """Streaming variant. Yields (event_dict, None) for each LLM chunk,
    then finally yields (None, Plan)."""
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=question),
    ]
    full_content: list[str] = []
    full_thinking: list[str] = []
    try:
        for ev in llm.chat_stream(messages, temperature=0.0):
            t = ev.get("type")
            if t in ("think", "content"):
                (full_thinking if t == "think" else full_content).append(ev.get("text", ""))
                yield ev, None
            elif t == "done":
                if not ev.get("content") and not full_content:
                    resp = llm.chat(messages, temperature=0.0)
                    full_content.append(resp.content)
                    full_thinking.append(resp.thinking or "")
    except Exception as e:
        log.warning(f"Streaming plan failed, falling back to non-stream: {e}")
        resp = llm.chat(messages, temperature=0.0)
        full_content.append(resp.content)
        full_thinking.append(resp.thinking or "")

    content = "".join(full_content)
    thinking = "".join(full_thinking)
    data = _parse_json(content)
    if not data:
        yield None, Plan(is_multi_step=False, steps=[], thinking=thinking)
        return
    try:
        is_multi = bool(data.get("is_multi_step", False))
        steps_raw = data.get("steps", []) or []
        steps = [
            PlanStep(
                id=int(s.get("id", idx + 1)),
                description=str(s.get("description", "")),
                action=str(s.get("action", "nl2sql")),
                depends_on=list(s.get("depends_on", []) or []),
            )
            for idx, s in enumerate(steps_raw[:max_steps])
        ]
        yield None, Plan(is_multi_step=is_multi, steps=steps, thinking=thinking)
    except Exception as e:
        log.warning(f"Failed to parse plan: {e}")
        yield None, Plan(is_multi_step=False, steps=[], thinking=thinking)
