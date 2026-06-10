"""Self-correction loop for failed SQL execution.

Strategy: re-prompt the LLM with the failing SQL + error message, ask it to
rewrite. Cap retries to avoid runaway token usage.
"""
from __future__ import annotations

from typing import Optional

from backend.llm.base import LLMClient, Message
from backend.utils import SQLError, get_logger

log = get_logger(__name__)

CORRECTION_PROMPT = """你之前生成的 SQL 在执行时出错了。

【原 SQL】
```sql
{sql}
```

【错误信息】
{error}

【数据库 Schema】
```
{schema_text}
```

请重新生成 SQL，修正错误。仅输出 SQL，不要解释。"""


def correct_sql(
    llm: LLMClient,
    *,
    original_sql: str,
    error_message: str,
    schema_text: str,
    system_prompt: str,
) -> str:
    """Ask the LLM to rewrite a failing SQL. Returns new SQL string."""
    messages = [
        Message(role="system", content=system_prompt),
        Message(
            role="user",
            content=CORRECTION_PROMPT.format(
                sql=original_sql, error=error_message, schema_text=schema_text
            ),
        ),
    ]
    resp = llm.chat(messages, temperature=0.0)
    return _strip_sql(resp.content)


def _strip_sql(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first fence
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # drop last fence
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text.rstrip(";").strip() + ";"
