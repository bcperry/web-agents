"""Streaming, usage, and content conversion helpers for chat responses."""

import json
import re
from typing import Any, AsyncGenerator, Optional

from agent_framework import Agent as RuntimeAgent
from agent_framework import AgentSession
from agent_framework._types import Content, Message as ChatMessage, UsageDetails

USAGE_INPUT_KEY = "input_token_count"
USAGE_OUTPUT_KEY = "output_token_count"
USAGE_TOTAL_KEY = "total_token_count"


def create_usage(
	input_token_count: Optional[int] = None,
	output_token_count: Optional[int] = None,
	total_token_count: Optional[int] = None,
) -> UsageDetails:
	return UsageDetails(
		input_token_count=input_token_count,
		output_token_count=output_token_count,
		total_token_count=total_token_count,
	)


def usage_value(usage: Optional[UsageDetails], key: str) -> int:
	if not usage:
		return 0
	if isinstance(usage, dict):
		return int(usage.get(key) or 0)
	return int(getattr(usage, key, 0) or 0)


def merge_usage(current: Optional[UsageDetails], incoming: Optional[UsageDetails]) -> Optional[UsageDetails]:
	if not incoming:
		return current
	if not current:
		return incoming
	return create_usage(
		input_token_count=usage_value(current, USAGE_INPUT_KEY) + usage_value(incoming, USAGE_INPUT_KEY),
		output_token_count=usage_value(current, USAGE_OUTPUT_KEY) + usage_value(incoming, USAGE_OUTPUT_KEY),
		total_token_count=usage_value(current, USAGE_TOTAL_KEY) + usage_value(incoming, USAGE_TOTAL_KEY),
	)


def extract_usage_from_payload(payload: dict) -> Optional[UsageDetails]:
	usage_data = payload.get("usage") or {}
	if not usage_data:
		return None
	return create_usage(
		input_token_count=usage_data.get(USAGE_INPUT_KEY),
		output_token_count=usage_data.get(USAGE_OUTPUT_KEY),
		total_token_count=usage_data.get(USAGE_TOTAL_KEY),
	)


def is_retryable_error(error: Exception) -> bool:
	error_message = str(error)
	error_type = str(type(error))
	error_lower = error_message.lower()
	return (
		"429" in error_message
		or "Too Many Requests" in error_message
		or "RateLimitError" in error_type
		or "rate_limit" in error_lower
		or "rate limit" in error_lower
		or "capacity" in error_lower
	)


def is_context_length_error(error: Exception) -> bool:
	error_text = str(error).lower()
	return any(
		phrase in error_text
		for phrase in [
			"context length",
			"maximum context length",
			"token limit",
			"too many tokens",
			"prompt is too long",
			"maximum prompt",
		]
	)


def sse_event(event: str, data: dict) -> str:
	return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def convert_content_items(items: object) -> list[dict[str, Any]]:
	if not isinstance(items, list):
		return []

	converted: list[dict[str, Any]] = []
	for item in items:
		if not isinstance(item, dict):
			continue
		item_type = item.get("type")
		if item_type == "text":
			converted.append({"type": "text", "text": item.get("text", "")})
		elif item_type == "data":
			uri = item.get("uri", "")
			if isinstance(uri, str) and uri.startswith("data:image/"):
				header, _, b64data = uri.partition(",")
				mime_type = header.split(";")[0].replace("data:", "")
				if b64data and mime_type:
					converted.append({"type": "image", "data": b64data, "mimeType": mime_type})
		elif item_type == "image" and item.get("data") and item.get("mimeType"):
			converted.append(item)
	return converted


def render_tool_result(result: object) -> str:
	if isinstance(result, list):
		text_parts = [
			item.get("text", "") for item in result
			if isinstance(item, dict) and item.get("type") == "text"
		]
		return "\n".join(text_parts) if text_parts else json.dumps(result, ensure_ascii=False)
	if isinstance(result, dict):
		return json.dumps(result, ensure_ascii=False)
	return str(result or "")


AGENT_VIEW_TOOL_NAME = "render_agent_view"


def agent_view_payload(tool_name: object, call_id: object, rendered_result: str) -> Optional[dict[str, Any]]:
	"""Map a ``render_agent_view`` result to an ``agent_view`` SSE payload.

	Returns None for other tools and for rejected renders — a rejection stays visible
	in the normal tool step so the agent can retry, but opens no pane.
	"""
	if tool_name != AGENT_VIEW_TOOL_NAME or not call_id:
		return None
	try:
		payload = json.loads(rendered_result)
	except (TypeError, ValueError):
		return None
	if not isinstance(payload, dict) or payload.get("status") != "rendered":
		return None
	view_id = payload.get("view_id")
	if not view_id:
		return None
	return {
		"view_id": str(view_id),
		"title": str(payload.get("title") or ""),
		"call_id": str(call_id),
		"created_at": str(payload.get("created_at") or ""),
	}


_USER_TIME_OPEN = "[Current date and time: "
_USER_TIME_CLOSE = "]\n\n"
_USER_TIME_RE = re.compile(r"^\[Current date and time: [^\]]*\]\n\n")


def with_user_time(text: str, when: str) -> str:
	"""Prepend a date/time marker to a user message for the model.

	The marker is stripped from the wire form by ``messages_to_wire`` so it stays
	invisible in the UI while remaining in the model-visible session history.
	"""
	return f"{_USER_TIME_OPEN}{when}{_USER_TIME_CLOSE}{text}"


def strip_user_time(text: str) -> str:
	"""Remove the ``with_user_time`` marker so resumed history renders cleanly."""
	return _USER_TIME_RE.sub("", text, count=1)


def messages_to_wire(messages: list[Any]) -> list[dict[str, Any]]:
	"""Map stored agent_framework ``Message`` objects to the frontend ``ChatMessage[]`` shape.

	Mirrors the framework's conversation-persistence sample: read each message's
	``role`` and ``text``. Only user/assistant turns that carry text become chat
	bubbles (tool-call/result messages have no display text).
	"""
	wire: list[dict[str, Any]] = []
	for msg in messages:
		role = getattr(msg, "role", None)
		role = getattr(role, "value", role)
		if role not in ("user", "assistant"):
			continue
		text = getattr(msg, "text", "") or ""
		if role == "user":
			text = strip_user_time(text)
		if not text:
			continue
		wire.append({"role": role, "content": text})
	return wire



async def stream_agent_response(
	agent: RuntimeAgent,
	contents: list[Content],
	session: AgentSession,
) -> AsyncGenerator[str, None]:
	request_usage: Optional[UsageDetails] = None
	final_text_parts: list[str] = []
	tool_events: list[dict[str, Any]] = []
	tool_event_by_call_id: dict[str, dict[str, Any]] = {}
	active_call_id: Optional[str] = None
	args_accumulator: dict[str, str] = {}

	user_message = ChatMessage(role="user", contents=contents)
	stream = agent.run(user_message, session=session, stream=True)

	async for msg in stream:
		msg_dict = msg.to_dict()

		update_usage = extract_usage_from_payload(msg_dict)
		request_usage = merge_usage(request_usage, update_usage)

		for content in msg_dict.get("contents", []) or []:
			content_type = content.get("type")

			if content_type == "function_call":
				call_id = content.get("call_id") or None
				name = content.get("name") or None
				arguments = content.get("arguments", "")
				rendered_arguments = json.dumps(arguments, ensure_ascii=False) if isinstance(arguments, (dict, list)) else str(arguments)

				if name and call_id and call_id not in tool_event_by_call_id:
					active_call_id = call_id
					args_accumulator[call_id] = rendered_arguments
					event_payload = {"call_id": call_id, "name": name, "arguments": rendered_arguments, "result": None}
					tool_events.append(event_payload)
					tool_event_by_call_id[call_id] = event_payload
					yield sse_event("function_call", {"call_id": call_id, "name": name, "arguments": rendered_arguments})
				elif call_id and call_id in tool_event_by_call_id:
					active_call_id = call_id
					if rendered_arguments:
						args_accumulator[call_id] = args_accumulator.get(call_id, "") + rendered_arguments
						tool_event_by_call_id[call_id]["arguments"] = args_accumulator[call_id]
						yield sse_event("function_call", {
							"call_id": call_id,
							"name": tool_event_by_call_id[call_id].get("name"),
							"arguments": args_accumulator[call_id],
						})
				elif active_call_id and rendered_arguments:
					args_accumulator[active_call_id] = args_accumulator.get(active_call_id, "") + rendered_arguments
					if active_call_id in tool_event_by_call_id:
						tool_event_by_call_id[active_call_id]["arguments"] = args_accumulator[active_call_id]
						yield sse_event("function_call", {
							"call_id": active_call_id,
							"name": tool_event_by_call_id[active_call_id].get("name"),
							"arguments": args_accumulator[active_call_id],
						})

			elif content_type == "mcp_server_tool_call":
				call_id = content.get("call_id") or None
				name = content.get("tool_name") or content.get("name") or None
				arguments = content.get("arguments", "")
				rendered_arguments = json.dumps(arguments, ensure_ascii=False) if isinstance(arguments, (dict, list)) else str(arguments)
				if name and call_id and call_id not in tool_event_by_call_id:
					args_accumulator[call_id] = rendered_arguments
					event_payload = {"call_id": call_id, "name": name, "arguments": rendered_arguments, "result": None}
					tool_events.append(event_payload)
					tool_event_by_call_id[call_id] = event_payload
					yield sse_event("function_call", {"call_id": call_id, "name": name, "arguments": rendered_arguments})

			elif content_type in ("function_result", "mcp_server_tool_result"):
				call_id = content.get("call_id")
				result = content.get("result") if content_type == "function_result" else content.get("output")
				converted = convert_content_items(content.get("items"))
				content_items = converted if any(item["type"] == "image" for item in converted) else None
				rendered_result = render_tool_result(result)
				accumulated_args = args_accumulator.get(call_id, "") if call_id else ""
				if call_id in tool_event_by_call_id:
					tool_event_by_call_id[call_id]["result"] = rendered_result
					tool_event_by_call_id[call_id]["arguments"] = accumulated_args
				active_call_id = None
				yield sse_event("function_result", {
					key: value for key, value in {
						"call_id": call_id,
						"result": rendered_result,
						"arguments": accumulated_args,
						"content_items": content_items,
					}.items() if value is not None
				})

				view_payload = agent_view_payload(
					(tool_event_by_call_id.get(call_id) or {}).get("name"), call_id, rendered_result
				)
				if view_payload:
					yield sse_event("agent_view", view_payload)

			elif content_type == "usage":
				usage = extract_usage_from_payload(content)
				request_usage = merge_usage(request_usage, usage)

		if getattr(msg, "text", None):
			final_text_parts.append(msg.text)
			yield sse_event("text", {"content": msg.text})

	try:
		final_response = await stream.get_final_response()
		if final_response and getattr(final_response, "usage_details", None):
			request_usage = merge_usage(request_usage, final_response.usage_details)
	except Exception:
		pass

	if request_usage:
		yield sse_event("usage", {
			USAGE_INPUT_KEY: usage_value(request_usage, USAGE_INPUT_KEY),
			USAGE_OUTPUT_KEY: usage_value(request_usage, USAGE_OUTPUT_KEY),
			USAGE_TOTAL_KEY: usage_value(request_usage, USAGE_TOTAL_KEY),
		})

	yield sse_event("done", {})
	stream_agent_response._last_result = {  # type: ignore[attr-defined]
		"text": "".join(final_text_parts).strip(),
		"tool_events": tool_events,
		"usage": request_usage,
	}


__all__ = [
	"USAGE_INPUT_KEY",
	"USAGE_OUTPUT_KEY",
	"USAGE_TOTAL_KEY",
	"agent_view_payload",
	"convert_content_items",
	"create_usage",
	"extract_usage_from_payload",
	"is_context_length_error",
	"is_retryable_error",
	"merge_usage",
	"render_tool_result",
	"sse_event",
	"stream_agent_response",
	"usage_value",
]