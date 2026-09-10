"""Notification sinks for autonomous run results.

Each completed autonomous cycle is delivered to a human-review channel. The
default :class:`LoggingSink` records a structured, non-secret summary (the
durable record is always the Cosmos run record); an optional :class:`WebhookSink`
POSTs the result JSON to a configured URL. Delivery failure is captured and
**non-fatal** — it never aborts the cycle or loses the audit record (FR-009).

No secrets: webhook destinations are resolved from environment-variable names
(or non-secret URLs) at runtime and are never logged or copied into a record.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# A notify.webhook value is treated as an env-var NAME when it matches this; the
# env var's value is then the URL. Otherwise it is treated as a literal URL.
_ENV_VAR_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_URL_RE = re.compile(r"https?://[^\s)]+")


def _webhook_timeout() -> float:
    try:
        return float(os.getenv("AUTONOMOUS_WEBHOOK_TIMEOUT", "10") or "10")
    except ValueError:
        return 10.0


@dataclass(frozen=True)
class NotificationResult:
    """Outcome of a delivery attempt, recorded on the run record."""

    status: str  # "logged" | "delivered" | "skipped" | "failed"
    error: str | None = None


def sanitize_error(message: str) -> str:
    """Strip URLs/tokens from an error so no secret leaks into a record or log."""
    sanitized = _URL_RE.sub("[URL]", str(message))
    sanitized = _BEARER_RE.sub("[REDACTED_TOKEN]", sanitized)
    return sanitized[:500]


@runtime_checkable
class NotificationSink(Protocol):
    """Delivers a (non-secret) run payload to a review channel."""

    async def deliver(self, payload: dict[str, Any]) -> NotificationResult: ...


class LoggingSink:
    """Default sink — logs a structured, non-secret summary of the run."""

    async def deliver(self, payload: dict[str, Any]) -> NotificationResult:
        logger.info(
            "Autonomous run notification (log): directive=%s status=%s tools=%d",
            payload.get("directiveId"),
            payload.get("status"),
            len(payload.get("toolEvents") or []),
        )
        return NotificationResult(status="logged")


class WebhookSink:
    """POSTs the run result JSON to a configured URL via ``httpx``.

    Delivery failure is caught and returned as ``failed`` (with a sanitized
    error); it never raises, so a failing webhook can never abort the cycle.
    """

    def __init__(self, url: str) -> None:
        self._url = url

    async def deliver(self, payload: dict[str, Any]) -> NotificationResult:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=_webhook_timeout()) as client:
                resp = await client.post(self._url, json=payload)
                resp.raise_for_status()
            return NotificationResult(status="delivered")
        except Exception as exc:  # noqa: BLE001 — delivery failure must be non-fatal
            error = sanitize_error(str(exc))
            logger.warning("Autonomous webhook delivery failed: %s", error)
            return NotificationResult(status="failed", error=error)


def _resolve_webhook(value: str | None) -> str | None:
    """Resolve a ``notify.webhook`` hint (env-var name or literal URL) to a URL."""
    if not value:
        return None
    value = value.strip()
    if _ENV_VAR_NAME_RE.match(value):
        resolved = (os.getenv(value) or "").strip()
        return resolved or None
    if value.lower().startswith(("https://", "http://")):
        return value
    return None


def resolve_webhook_url(directive: Any) -> str | None:
    """Resolve the effective webhook URL for a directive (per-directive, then global)."""
    directive_hint: str | None = None
    notify = getattr(directive, "notify", None)
    if isinstance(notify, dict):
        directive_hint = notify.get("webhook")
    return _resolve_webhook(directive_hint) or _resolve_webhook(
        os.getenv("AUTONOMOUS_NOTIFY_WEBHOOK_URL")
    )


def build_notification_sink(directive: Any) -> NotificationSink:
    """Resolve the sink for a directive: a webhook if one resolves, else logging."""
    url = resolve_webhook_url(directive)
    if url:
        return WebhookSink(url)
    return LoggingSink()


def notify_descriptor(directive: Any) -> str:
    """Non-secret descriptor for the directives API: ``"webhook"`` or ``"log"``."""
    return "webhook" if resolve_webhook_url(directive) else "log"


__all__ = [
    "LoggingSink",
    "NotificationResult",
    "NotificationSink",
    "WebhookSink",
    "build_notification_sink",
    "notify_descriptor",
    "resolve_webhook_url",
    "sanitize_error",
]
