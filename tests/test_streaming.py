"""Tests for streaming, usage, and error helpers."""

import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from agent_framework._types import UsageDetails

from streaming import (
    USAGE_INPUT_KEY,
    USAGE_OUTPUT_KEY,
    USAGE_TOTAL_KEY,
    agent_view_payload,
    convert_content_items,
    create_usage,
    extract_usage_from_payload,
    is_context_length_error,
    is_retryable_error,
    merge_usage,
    render_tool_result,
    sse_event,
    usage_value,
)


def test_usage_helpers_create_extract_and_merge_counts():
    first = create_usage(input_token_count=1, output_token_count=2, total_token_count=3)
    second = extract_usage_from_payload({"usage": {USAGE_INPUT_KEY: 4, USAGE_OUTPUT_KEY: 5, USAGE_TOTAL_KEY: 9}})

    merged = merge_usage(first, second)

    assert usage_value(merged, USAGE_INPUT_KEY) == 5
    assert usage_value(merged, USAGE_OUTPUT_KEY) == 7
    assert usage_value(merged, USAGE_TOTAL_KEY) == 12
    assert merge_usage(None, second) is second
    assert extract_usage_from_payload({}) is None


def test_usage_value_handles_dicts_and_none():
    assert usage_value(None, USAGE_INPUT_KEY) == 0
    assert usage_value({USAGE_INPUT_KEY: 7}, USAGE_INPUT_KEY) == 7
    assert usage_value(UsageDetails(input_token_count=8), USAGE_INPUT_KEY) == 8


def test_sse_event_preserves_event_name_and_json_payload():
    rendered = sse_event("text", {"content": "hello"})
    assert rendered.startswith("event: text\n")
    assert rendered.endswith("\n\n")
    payload = json.loads(rendered.split("data: ", 1)[1])
    assert payload == {"content": "hello"}


def test_error_classifiers_match_current_behavior():
    assert is_retryable_error(Exception("429 Too Many Requests")) is True
    assert is_retryable_error(Exception("service at capacity")) is True
    assert is_retryable_error(Exception("Connection timeout")) is False

    assert is_context_length_error(Exception("maximum context length exceeded")) is True
    assert is_context_length_error(Exception("too many tokens")) is True
    assert is_context_length_error(Exception("ordinary failure")) is False


def test_convert_content_items_filters_and_normalizes_images():
    converted = convert_content_items([
        {"type": "text", "text": "hello"},
        {"type": "data", "uri": "data:image/png;base64,abc123"},
        {"type": "data", "uri": "data:application/pdf;base64,nope"},
        {"type": "image", "data": "xyz", "mimeType": "image/jpeg"},
        "skip me",
    ])

    assert converted == [
        {"type": "text", "text": "hello"},
        {"type": "image", "data": "abc123", "mimeType": "image/png"},
        {"type": "image", "data": "xyz", "mimeType": "image/jpeg"},
    ]


def test_render_tool_result_matches_current_display_behavior():
    assert render_tool_result([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a\nb"
    assert render_tool_result({"ok": True}) == '{"ok": true}'
    assert render_tool_result(None) == ""


def test_render_tool_result_encodes_structured_values_without_losing_false_or_zero():
    assert render_tool_result(False) == "false"
    assert render_tool_result(0) == "0"
    assert render_tool_result("True and None are words") == "True and None are words"
    assert json.loads(render_tool_result({
        "when": datetime(2026, 9, 10, tzinfo=timezone.utc),
        "id": UUID(int=0), "values": [False, 0, None],
    })) == {
        "when": "2026-09-10T00:00:00+00:00",
        "id": "00000000-0000-0000-0000-000000000000", "values": [False, 0, None],
    }


def test_agent_view_payload_maps_a_rendered_result():
    result = json.dumps({
        "status": "rendered",
        "view_id": "v-1",
        "title": "Readiness",
        "chars": 42,
        "created_at": "2026-08-14T00:00:00+00:00",
    })

    payload = agent_view_payload("render_agent_view", "call-1", result)

    assert payload == {
        "view_id": "v-1",
        "title": "Readiness",
        "call_id": "call-1",
        "created_at": "2026-08-14T00:00:00+00:00",
    }


def test_agent_view_payload_skips_rejections_and_other_tools():
    rejected = json.dumps({"status": "rejected", "reason": "too_large"})

    assert agent_view_payload("render_agent_view", "call-1", rejected) is None
    assert agent_view_payload("get_user_profile", "call-1", '{"status": "rendered", "view_id": "v"}') is None
    assert agent_view_payload("render_agent_view", None, '{"status": "rendered", "view_id": "v"}') is None
    assert agent_view_payload("render_agent_view", "call-1", "not json") is None
    assert agent_view_payload("render_agent_view", "call-1", '{"status": "rendered"}') is None


@pytest.mark.parametrize("result_type, result_key", [("function_result", "result"), ("mcp_server_tool_result", "output")])
@pytest.mark.parametrize("tool_output", ["tool text", {"ok": True}])
def test_structured_stream_and_sse_publish_request_local_results(result_type, result_key, tool_output):
    import asyncio
    from types import SimpleNamespace
    from agent_framework import AgentResponseUpdate, Content
    from streaming import stream_agent_events, stream_agent_response

    class Stream:
        def __aiter__(self):
            async def updates():
                yield AgentResponseUpdate(contents=[Content.from_text("hello")])
                yield SimpleNamespace(text=None, to_dict=lambda: {"contents": [
                    {"type": "function_call", "call_id": "call-1", "name": "lookup", "arguments": '{"id":'},
                    {"type": "function_call", "arguments": '1'},
                    {"type": "function_call", "call_id": "call-2", "name": "other", "arguments": '{}'},
                    {"type": "function_call", "call_id": "call-1", "arguments": '}'},
                    {"type": "mcp_server_tool_call", "call_id": "call-3", "tool_name": "remote", "arguments": {}},
                    {"type": result_type, "call_id": "call-1", result_key: tool_output},
                ]})
            return updates()

        async def get_final_response(self):
            return SimpleNamespace(usage_details=create_usage(total_token_count=3))

    async def scenario():
        agent = SimpleNamespace(run=lambda *args, **kwargs: Stream())
        result = {}
        events = [event async for event in stream_agent_events(agent, [], None, result=result)]
        assert events[0] == ("text", {"content": "hello"})
        assert events[-1] == ("done", {})
        assert result["text"] == "hello"
        assert result["tool_events"][0]["result"] == render_tool_result(tool_output)
        assert [event["call_id"] for event in result["tool_events"]] == ["call-1", "call-2", "call-3"]
        assert result["tool_events"][0]["arguments"] == '{"id":1}'
        assert [payload["arguments"] for kind, payload in events if kind == "function_result"] == ['{"id":1}']
        other_result = {}
        encoded = [event async for event in stream_agent_response(agent, [], None, result=other_result)]
        assert encoded[0].startswith("event: text\n")
        assert other_result == result
        assert not hasattr(stream_agent_response, "_last_result")
    asyncio.run(scenario())