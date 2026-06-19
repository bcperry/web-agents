# Contract: `config/autonomous.yaml` Schema

The operational configuration for Autonomous Mode. Loaded and validated by `autonomous.py`
(`load_directives()` / `load_autonomous_config()`). References agent profiles from
`config/agents.yaml` by id. Contains **no secrets** — webhook destinations are referenced by
environment-variable name or supplied as non-secret URLs resolved at runtime.

## Top-level schema

```yaml
schema_version: 1
enabled: true                      # master switch; env AUTONOMOUS_ENABLED overrides
system_user_id: autonomous-duty-officer   # owner identity; env AUTONOMOUS_USER_ID overrides

directives:
  - id: duty-officer-watch         # required, unique
    profile_id: chief-of-staff     # required, must reference an agents.yaml profile
    enabled: true                  # optional, default true
    schedule: "0 */15 * * * *"     # NCRONTAB (6-field, seconds-first); drives the in-process scheduler
    instruction: |                 # required, the standing prompt executed each cycle
      You are the on-watch duty officer. Perform the standing watch check:
      summarize the current operational picture from the staff sections,
      flag anything that requires command attention, and draft a concise
      watch note suitable for the GCC Watch to review. If nothing requires
      attention, say so explicitly.
    notify:                        # optional routing; omit for log-only
      webhook: AUTONOMOUS_NOTIFY_WEBHOOK_URL   # env-var name OR a literal https URL
```

## Field rules

| Field | Required | Type | Validation |
|-------|----------|------|------------|
| `schema_version` | no | int | If present, must be `1`. |
| `enabled` | no | bool | Default `true`. Env `AUTONOMOUS_ENABLED` (`true`/`false`) overrides. |
| `system_user_id` | no | string | Default `autonomous-duty-officer`. Env `AUTONOMOUS_USER_ID` overrides. |
| `directives` | yes | list | Must contain ≥ 1 entry for any cycle to run. |
| `directives[].id` | yes | string | Non-empty; unique across the list. |
| `directives[].profile_id` | yes | string | Non-empty; resolved against `agents.yaml` at cycle time (missing → recorded failed run). |
| `directives[].instruction` | yes | string | Non-empty. |
| `directives[].enabled` | no | bool | Default `true`. |
| `directives[].schedule` | no | string | NCRONTAB (6-field, seconds-first). The in-process scheduler fires the directive when this is due. Omit to exclude from the schedule (still runnable via run-now). |
| `directives[].notify` | no | object | `{ webhook: <env-var-name \| https-url> }`. |

## Resolution semantics

- **Master gate**: a directive runs only if global `enabled` AND `directives[].enabled` are
  both true. Env `AUTONOMOUS_ENABLED=false` disables everything (the disabled no-op).
- **Scheduler gate**: the unattended in-process scheduler runs only when
  `AUTONOMOUS_SCHEDULER_ENABLED` is truthy (off by default locally; an empty value defaults to
  enabled in the deployed App Service). `run-now` works regardless of this flag.
- **Default directive**: a `POST /api/autonomous/run-now` with no `directive_id` runs the
  **first enabled** directive in list order; the scheduler independently considers every
  enabled directive that has a `schedule`.
- **Webhook resolution**: `notify.webhook` is treated as an environment-variable name if it
  matches `^[A-Z][A-Z0-9_]*$` and that env var is set (its value is the URL); otherwise it is
  treated as a literal URL. If neither resolves, the directive falls back to the global
  `AUTONOMOUS_NOTIFY_WEBHOOK_URL`, and if that is unset, to the `LoggingSink`.
- **Missing file**: if `config/autonomous.yaml` is absent, the feature is treated as
  **disabled** with zero directives (safe no-op), not an error.

## Security

- The file MUST NOT contain webhook secrets; only env-var **names** or non-secret URLs. Any
  webhook secret lives in app settings / Key Vault, never in this file or in version control.
  (There is no autonomous trigger key — the schedule runs in-process.)
