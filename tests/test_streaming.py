"""Tests for streaming, usage, and error helpers."""

import json

from agent_framework._types import UsageDetails

from streaming import (
    USAGE_INPUT_KEY,
    USAGE_OUTPUT_KEY,
    USAGE_TOTAL_KEY,
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