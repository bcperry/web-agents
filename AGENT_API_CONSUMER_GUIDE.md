# Agent API Consumer Guide

This guide describes how an external application can select an agent, create a chat session, send text and pictures, and consume the streamed response.

## Prerequisites

Obtain these values from the API owner:

- `BASE_URL`: The deployed application URL, such as `https://example.azurewebsites.us`.
- `TOKEN`: An Entra ID bearer token accepted by the application.
- `PROFILE_ID`: The ID of the agent to query.

Send the token on every request:

```http
Authorization: Bearer <TOKEN>
```

The token must be issued for the application configured by the API owner. A missing, expired, or incorrectly scoped token returns HTTP `401`.

## 1. Discover Available Agents

Call `GET /api/profiles`:

```bash
curl --fail-with-body \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/profiles"
```

Example response:

```json
{
  "profiles": [
    {
      "id": "general",
      "name": "General Agent",
      "description": "General-purpose assistant",
      "icon": "bot",
      "group": "",
      "starters": [],
      "skills": [],
      "mcp_server_count": 0
    }
  ],
  "unavailable": []
}
```

Use a value from `profiles[].id` as `profile_id` when creating the session.

## 2. Create a Session

Call `POST /api/sessions` with JSON:

```bash
SESSION_RESPONSE=$(curl --fail-with-body \
  -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"profile_id":"general"}' \
  "$BASE_URL/api/sessions")

SESSION_ID=$(printf '%s' "$SESSION_RESPONSE" | jq -r '.session_id')
```

Minimal request schema for a built-in agent:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["profile_id"],
  "properties": {
    "profile_id": { "type": "string", "minLength": 1 },
    "conversation_id": { "type": "string", "minLength": 1 }
  },
  "additionalProperties": true
}
```

`conversation_id` is optional and is used only when resuming an existing conversation.

Example HTTP `201` response:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "profile_id": "general",
  "profile_name": "General Agent",
  "tools_loaded": [],
  "skills_loaded": [],
  "agents_loaded": [],
  "search_context": false,
  "mcp_results": [],
  "used_profile_override": false,
  "override_updated_at": null
}
```

Keep `session_id`. It is required for subsequent messages.

## 3. Send a Text Message

For text without pictures, send JSON to `POST /api/sessions/{session_id}/messages`:

```bash
curl --no-buffer --fail-with-body \
  -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "content": "Summarize the current situation.",
    "client_time": "2026-09-03T14:30:00Z"
  }' \
  "$BASE_URL/api/sessions/$SESSION_ID/messages"
```

`client_time` is optional. When omitted, the server uses the current UTC time.

## 4. Send Pictures

Picture input uses `multipart/form-data`. Each picture must be sent as a binary file part named `images`. The text fields are named `content` and `client_time`.

```bash
curl --no-buffer --fail-with-body \
  -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -F 'content=Describe these pictures and compare what they show.' \
  -F 'client_time=2026-09-03T14:30:00Z' \
  -F 'images=@./front-view.png;type=image/png' \
  -F 'images=@./side-view.jpg;type=image/jpeg' \
  "$BASE_URL/api/sessions/$SESSION_ID/messages"
```

Do not manually set the `Content-Type` header for this request. The HTTP client must generate the multipart boundary.

Picture constraints:

- Supported types: JPEG, PNG, GIF, and WebP.
- Maximum pictures per message: 5.
- Maximum size per picture: 400 MB.
- The declared MIME type must match the file's actual signature.

### Starting With Base64

The API does not accept a base64 string in the message JSON. If the caller starts with base64 data, decode it into bytes and attach those bytes as an `images` multipart part.

Browser JavaScript example:

```js
const base64 = "iVBORw0KGgoAAA...";
const mimeType = "image/png";
const filename = "picture.png";

const bytes = Uint8Array.from(atob(base64), character => character.charCodeAt(0));
const picture = new Blob([bytes], { type: mimeType });

const form = new FormData();
form.append("content", "What does this picture show?");
form.append("client_time", new Date().toISOString());
form.append("images", picture, filename);

const response = await fetch(`${baseUrl}/api/sessions/${sessionId}/messages`, {
  method: "POST",
  headers: { Authorization: `Bearer ${token}` },
  body: form
});

if (!response.ok) {
  throw new Error(`Agent request failed: ${response.status} ${await response.text()}`);
}
```

For a data URL such as `data:image/png;base64,...`, remove the prefix through the first comma before decoding.

## 5. Consume the Response Stream

The message endpoint returns `Content-Type: text/event-stream`. It does not return one JSON response document. Each server-sent event has an event name and a JSON payload:

```text
event: text
data: {"content":"The first picture shows "}

event: text
data: {"content":"a vehicle viewed from the front."}

event: usage
data: {"input_token_count":1250,"output_token_count":42,"total_token_count":1292}

event: done
data: {}

```

Concatenate `content` from all `text` events, in arrival order, to construct the final answer. Stop after `done`.

A message may also produce tool events:

```text
event: function_call
data: {"call_id":"call-1","name":"lookup","arguments":"{\"id\":123}"}

event: function_result
data: {"call_id":"call-1","result":"Found record 123","arguments":"{\"id\":123}"}

```

Possible event payloads:

```json
{
  "text": {
    "content": "string"
  },
  "function_call": {
    "call_id": "string",
    "name": "string",
    "arguments": "JSON encoded as a string"
  },
  "function_result": {
    "call_id": "string or null",
    "result": "string",
    "arguments": "string",
    "content_items": [
      {
        "type": "image",
        "data": "base64 image bytes",
        "mimeType": "image/png"
      }
    ]
  },
  "usage": {
    "input_token_count": 0,
    "output_token_count": 0,
    "total_token_count": 0
  },
  "error": {
    "message": "string",
    "retry_after": 30
  },
  "agent_view": {
    "view_id": "string",
    "title": "string",
    "call_id": "string",
    "created_at": "string"
  },
  "done": {}
}
```

`content_items` is optional. If a tool returns a picture, its `data` field is base64 without a data-URL prefix. This output representation is separate from picture input, which uses multipart binary files.

A stream-level `error` event can arrive after an HTTP `200`. Treat it as a failed agent turn, honor `retry_after` when present, and continue reading until `done`.

Browser `EventSource` cannot POST a request body. Use `fetch()` and parse `response.body`, or use an SSE client that supports POST requests.

## 6. End the Session

When finished, release the active session:

```bash
curl --fail-with-body \
  -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/sessions/$SESSION_ID"
```

A successful deletion returns HTTP `204` with no body.

## HTTP Errors

Handle non-success HTTP statuses before parsing the SSE stream:

- `400`: Invalid profile, oversized text, too many pictures, unsupported MIME type, oversized picture, or corrupt/mislabeled picture.
- `401`: Missing, invalid, or expired bearer token.
- `404`: Session does not exist or is no longer active.
- `500`: Server authentication or agent configuration error.

Session state is server-side. Always create a session before sending a message, keep the same bearer identity for the session, and create a new session if the previous one is no longer active.
