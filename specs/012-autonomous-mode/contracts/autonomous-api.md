# Contract: Autonomous Backend API (`/api/autonomous/*`)

All endpoints are served by the existing FastAPI backend (the agent host). The **scheduled**
path runs **in-process** (the `AutonomousScheduler`) and exposes **no HTTP endpoint**. Every
endpoint below is the standard **authenticated-user** API; there is no service-to-service key.

## Authentication

- **User auth (all endpoints)**: existing `get_current_user` (Azure AD bearer in prod;
  `AUTH_DISABLED=true` bypass for local dev). Unauthenticated calls → `401` outside local dev.
- There is **no `X-Autonomous-Key` / `AUTONOMOUS_TRIGGER_KEY`** — the schedule runs in-process,
  so there is no external trigger to authenticate.
- Tokens/secrets are never echoed in responses or logs.

---

## POST /api/autonomous/run-now

Run one autonomous cycle on demand for a directive and return its run record (each call
creates a new run). This is the **only** way to trigger a cycle over HTTP; scheduled cycles
fire in-process and are recorded as `trigger: "timer"`.

### Request

Headers: `Authorization: Bearer <token>` (or dev bypass), `Content-Type: application/json`

Body:
```json
{
  "directive_id": "duty-officer-watch"   // optional; if omitted, runs the first enabled directive
}
```

### Responses

`200 OK` — cycle completed (success **or** captured failure; both produce a run record):
```json
{
  "id": "9f1c2e7a8b...",
  "directiveId": "duty-officer-watch",
  "profileId": "chief-of-staff",
  "sessionId": "f3a1...",
  "status": "success",
  "startedAt": "2026-06-18T17:40:00Z",
  "finishedAt": "2026-06-18T17:40:12Z",
  "responseText": "Watch summary: ...",
  "toolEvents": [ { "name": "...", "arguments": "...", "result": "..." } ],
  "usage": { "input_token_count": 1234, "output_token_count": 567, "total_token_count": 1801 },
  "error": null,
  "notifyStatus": "logged",
  "notifyError": null,
  "trigger": "manual"
}
```

`401 Unauthorized` — no valid user session (outside local dev). No cycle runs.

`404 Not Found` — `directive_id` provided but not found / not enabled.

`409 Conflict` — autonomous mode disabled (`enabled: false`) — the cycle is a no-op by
configuration (alternatively represented as `204`/`200` with a `disabled` status; the
implementation returns `409` with a clear message so the trigger can log it).

`502 Bad Gateway` / `500` — unexpected server error (the cycle could not be recorded at all).

### Behavior

- Resolves the directive (explicit `directive_id` or the first enabled one).
- Builds a session for the directive's `profile_id` owned by the system identity, sends the
  directive `instruction`, collects the full response (text + tool events + usage).
- Persists exactly one `autonomous-runs` record (success or failure).
- Delivers to the notification sink; delivery failure is recorded, not fatal.

---

## GET /api/autonomous/runs

List autonomous run history, most-recent-first.

### Request

Headers: `Authorization: Bearer <token>` (or dev bypass).

Query params: `limit` (default `50`, max `200`), `directive_id` (optional — scope to one
directive's partition; otherwise a bounded cross-partition recency query).

### Response

`200 OK`:
```json
{
  "runs": [ { /* run wire shape as above */ } ],
  "count": 12
}
```

---

## GET /api/autonomous/directives

List the configured directives (no secrets).

### Response

`200 OK`:
```json
{
  "enabled": true,
  "systemUserId": "autonomous-duty-officer",
  "directives": [
    {
      "id": "duty-officer-watch",
      "profileId": "chief-of-staff",
      "instructionSummary": "Perform the standing watch check ...",
      "schedule": "0 */15 * * * *",
      "enabled": true,
      "notify": "webhook" 
    }
  ]
}
```

- `instructionSummary` is a truncated preview (full instruction is config-side).
- `notify` is a non-secret descriptor (`"webhook"` | `"log"`), never the URL/secret.

---

## GET /api/autonomous/conversations

List the shared Duty Officer conversation threads (read-only, visible to every signed-in
user). Each directive runs in one ongoing conversation owned by the system identity, so this
is the durable watch log — most-recently-active first.

`200 OK`:
```json
{ "conversations": [ { "id": "autonomous-duty-officer-watch", "profileId": "G-6 Signal", "profileName": "G-6 Signal", "lastActivityAt": "2026-06-18T17:40:12Z" } ] }
```

## GET /api/autonomous/conversations/{id}/messages

Read the (read-only) transcript of a shared Duty Officer conversation. Ownership is checked
against the system identity, so only autonomous threads are readable here — never an arbitrary
user's private conversation (a non-autonomous id → `404`).

`200 OK`: `{ "id": "...", "profileId": "...", "profileName": "...", "messages": [ { "role": "user|assistant", "content": "..." } ] }`

---

## Error envelope

Errors reuse FastAPI's `{"detail": "<message>"}` shape, consistent with the rest of the API.
Messages never include secrets or raw credential values (sanitized).
