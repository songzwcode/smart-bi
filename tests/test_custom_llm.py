"""Tests for backend.llm.custom (OpenAI-compatible HTTP LLM client)."""
from __future__ import annotations

import json
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from backend.llm.base import Message, ToolCall
from backend.llm.custom import CustomClient, _from_openai_response, _to_openai_messages
from backend.utils import LLMError


# ---- helpers -----------------------------------------------------------------


def _ok_response(content: str = "Hello", model: str = "minimax-m3") -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _tool_call_response() -> dict:
    return {
        "model": "minimax-m3",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "run_sql",
                                "arguments": json.dumps({"sql": "SELECT 1"}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 20},
    }


# ---- _to_openai_messages ----------------------------------------------------


def test_to_openai_messages_simple():
    msgs = [Message(role="system", content="sys"), Message(role="user", content="hi")]
    out = _to_openai_messages(msgs)
    assert out[0] == {"role": "system", "content": "sys"}
    assert out[1] == {"role": "user", "content": "hi"}


def test_to_openai_messages_tool():
    msgs = [Message(role="tool", content="result", tool_call_id="call_x")]
    out = _to_openai_messages(msgs)
    assert out[0]["role"] == "tool"
    assert out[0]["tool_call_id"] == "call_x"
    assert out[0]["content"] == "result"


def test_to_openai_messages_assistant_with_tool_calls():
    msgs = [
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(name="foo", arguments={"a": 1}, id="c1")],
        )
    ]
    out = _to_openai_messages(msgs)
    assert out[0]["role"] == "assistant"
    assert out[0]["tool_calls"][0]["function"]["name"] == "foo"
    assert json.loads(out[0]["tool_calls"][0]["function"]["arguments"]) == {"a": 1}


# ---- _from_openai_response --------------------------------------------------


def test_from_openai_response_text():
    r = _from_openai_response(_ok_response("hi"), model="minimax-m3")
    assert r.content == "hi"
    assert r.model == "minimax-m3"
    assert r.tool_calls == []
    assert r.usage["total_tokens"] == 15


def test_from_openai_response_with_tool_calls():
    r = _from_openai_response(_tool_call_response(), model="minimax-m3")
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0].name == "run_sql"
    assert r.tool_calls[0].arguments == {"sql": "SELECT 1"}
    assert r.tool_calls[0].id == "call_1"


def test_from_openai_response_malformed_args_falls_back_to_empty():
    bad = {
        "model": "x",
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "1",
                            "function": {"name": "f", "arguments": "not-json{"},
                        }
                    ]
                }
            }
        ],
    }
    r = _from_openai_response(bad, model="x")
    assert r.tool_calls[0].arguments == {}


# ---- CustomClient init ------------------------------------------------------


def test_init_requires_base_url():
    with pytest.raises(LLMError) as e:
        CustomClient(model="m", base_url="")
    assert "base_url" in str(e.value)


def test_init_strips_trailing_slash():
    c = CustomClient(model="m", base_url="https://x.com/v1/", api_key="k")
    assert c.base_url == "https://x.com/v1"


# ---- CustomClient.chat ------------------------------------------------------


def test_chat_text_completion():
    c = CustomClient(model="minimax-m3", base_url="https://api.test/v1", api_key="sk-test")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _ok_response("Hello, world!")
    with patch.object(c._client, "post", return_value=mock_resp) as post:
        r = c.chat([Message(role="user", content="hi")])
    assert r.content == "Hello, world!"
    # Verify URL + headers
    args, kwargs = post.call_args
    assert args[0] == "https://api.test/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert kwargs["json"]["model"] == "minimax-m3"
    assert kwargs["json"]["messages"] == [{"role": "user", "content": "hi"}]


def test_chat_with_tools_sends_tools_and_tool_choice():
    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _ok_response("ok")
    with patch.object(c._client, "post", return_value=mock_resp) as post:
        c.chat(
            [Message(role="user", content="hi")],
            tools=[{"name": "run_sql", "description": "exec", "parameters": {}}],
        )
    payload = post.call_args.kwargs["json"]
    assert payload["tools"] == [{"type": "function", "function": {"name": "run_sql", "description": "exec", "parameters": {}}}]
    assert payload["tool_choice"] == "auto"


def test_chat_with_max_tokens():
    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _ok_response()
    with patch.object(c._client, "post", return_value=mock_resp) as post:
        c.chat([Message(role="user", content="hi")], max_tokens=128)
    assert post.call_args.kwargs["json"]["max_tokens"] == 128


def test_chat_http_error_raises():
    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "unauthorized"
    with patch.object(c._client, "post", return_value=mock_resp):
        with pytest.raises(LLMError) as e:
            c.chat([Message(role="user", content="hi")])
    assert "401" in str(e.value)


def test_chat_network_error_raises():
    import httpx

    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    with patch.object(c._client, "post", side_effect=httpx.ConnectError("nope")):
        with pytest.raises(LLMError):
            c.chat([Message(role="user", content="hi")])


def test_chat_invalid_json_raises():
    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = json.JSONDecodeError("e", "x", 0)
    with patch.object(c._client, "post", return_value=mock_resp):
        with pytest.raises(LLMError) as e:
            c.chat([Message(role="user", content="hi")])
    assert "JSON" in str(e.value)


# ---- CustomClient.list_models -----------------------------------------------


def test_list_models_returns_model_ids():
    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "minimax-m3"}, {"id": "other-model"}]}
    with patch.object(c._client, "get", return_value=mock_resp):
        models = c.list_models()
    assert models == ["minimax-m3", "other-model"]


def test_list_models_falls_back_on_error():
    c = CustomClient(model="minimax-m3", base_url="https://x/v1", api_key="k")
    with patch.object(c._client, "get", side_effect=Exception("boom")):
        models = c.list_models()
    assert models == ["minimax-m3"]


# ---- CustomClient.test_connectivity -----------------------------------------


def test_test_connectivity_ok():
    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch.object(c._client, "get", return_value=mock_resp):
        r = c.test_connectivity()
    assert r["ok"] is True
    assert r["status_code"] == 200
    assert r["url"] == "https://x/v1/models"


def test_test_connectivity_unreachable():
    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    with patch.object(c._client, "get", side_effect=Exception("connect failed")):
        r = c.test_connectivity()
    assert r["ok"] is False
    assert "connect failed" in r["error"]


# ---- factory integration ----------------------------------------------------


def test_factory_creates_custom_client():
    from backend.llm.factory import create_llm

    c = create_llm(provider="custom", model="minimax-m3", custom_url="https://api.test/v1", custom_api_key="k")
    assert isinstance(c, CustomClient)
    assert c.model == "minimax-m3"
    assert c.base_url == "https://api.test/v1"
    assert c.api_key == "k"


# ---- think-tag stripping (reasoning models) --------------------------------


def test_strip_think_in_content():
    from backend.llm.custom import _strip_think

    r = _from_openai_response(
        {
            "model": "x",
            "choices": [{"message": {"content": "<think>internal</think>SELECT 1"}}],
        },
        model="x",
    )
    assert r.content == "SELECT 1"


def test_strip_think_in_tool_arguments():
    bad = {
        "model": "x",
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "1",
                            "function": {
                                "name": "f",
                                "arguments": "<think>reasoning</think>" + json.dumps({"sql": "SELECT 1"}),
                            },
                        }
                    ]
                }
            }
        ],
    }
    r = _from_openai_response(bad, model="x")
    assert r.tool_calls[0].arguments == {"sql": "SELECT 1"}


def test_strip_think_multiline():
    from backend.llm.custom import _strip_think

    txt = "<think>\nthis is\nmultiline\n</think>SELECT * FROM t"
    assert _strip_think(txt) == "SELECT * FROM t"


# ---- chat_stream event contract ---------------------------------------------


def _make_stream_response(lines: list[str]):
    """Build a mock httpx response for streaming POST."""
    import httpx

    def iter_lines():
        for ln in lines:
            yield ln

    resp = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.raise_for_status = MagicMock()
    resp.iter_lines = iter_lines
    return resp


def test_chat_stream_emits_think_and_content_events():
    """Streaming response should emit think/content/done events."""
    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    chunks = [
        'data: {"choices":[{"delta":{"content":"<think>reason"}}]}',
        'data: {"choices":[{"delta":{"content":"ing here</think>"}}]}',
        'data: {"choices":[{"delta":{"content":"SELECT 1"}}]}',
        'data: [DONE]',
    ]
    mock_resp = _make_stream_response(chunks)
    with patch.object(c._client, "stream", return_value=mock_resp):
        events = list(c.chat_stream([Message(role="user", content="hi")]))
    types = [e["type"] for e in events]
    assert "think" in types
    assert "content" in types
    assert types[-1] == "done"
    done = events[-1]
    assert done["content"] == "SELECT 1"
    assert "reasoning here" in done["thinking"]


def test_chat_stream_content_only():
    c = CustomClient(model="m", base_url="https://x/v1", api_key="k")
    chunks = [
        'data: {"choices":[{"delta":{"content":"hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        'data: [DONE]',
    ]
    mock_resp = _make_stream_response(chunks)
    with patch.object(c._client, "stream", return_value=mock_resp):
        events = list(c.chat_stream([Message(role="user", content="hi")]))
    done = events[-1]
    assert done["content"] == "hello world"
    assert done["thinking"] == ""
