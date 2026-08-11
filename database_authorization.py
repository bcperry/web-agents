"""Entitlement authorization and metadata-only auditing for database tools.

The authorizer is the single boundary that decides whether an authenticated
application user may *receive* or *invoke* a provider-bound database capability.
It re-evaluates Entra membership before every invocation, caches resolved
membership for at most five minutes, and fails closed on any resolution error.

Every attempt (tool exposure, denial, or completed invocation) emits exactly one
metadata-only audit event. SQL text/hashes, parameter values, result cells,
credentials, connection metadata, and raw driver errors never reach the sink.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from database import (
    AgentDatabaseGrant,
    AuthorizationError,
    Capability,
    Environment,
    QueryStatus,
    new_correlation_id,
)

logger = logging.getLogger(__name__)

MAX_MEMBERSHIP_CACHE_SECONDS = 300

DENIED_MESSAGE = "Your account is not entitled to use this database capability."

OUTCOME_ALLOWED = "allowed"
OUTCOME_DENIED = "denied"
OUTCOME_ERROR = "error"


class DenialReason(str, Enum):
    """Sanitized denial categories that are safe to audit and return."""

    TENANT_NOT_CONFIGURED = "tenant_not_configured"
    CAPABILITY_NOT_GRANTED = "capability_not_granted"
    ENVIRONMENT_MISMATCH = "environment_mismatch"
    NOT_ENTITLED = "not_entitled"
    MEMBERSHIP_UNRESOLVED = "membership_unresolved"


class MembershipResolutionError(AuthorizationError):
    """Raised when transitive group membership cannot be proven."""


# ---------------------------------------------------------------------------
# Injected collaborators
# ---------------------------------------------------------------------------


@runtime_checkable
class GroupMembershipResolver(Protocol):
    """Resolves transitive Entra group membership for one user.

    The production implementation calls Microsoft Graph with the trusted backend
    identity. Implementations may be sync or async and must raise rather than
    return a partial set when membership cannot be proven.
    """

    def resolve_transitive_group_ids(self, *, user_id: str, tenant_id: str) -> Iterable[str]:
        ...


class FailClosedGroupMembershipResolver:
    """Default resolver: no resolution capability means no entitlement."""

    def resolve_transitive_group_ids(self, *, user_id: str, tenant_id: str) -> Iterable[str]:
        raise MembershipResolutionError(
            "Group membership could not be resolved; no membership resolver is configured."
        )


@dataclass(frozen=True)
class DatabaseAuditEvent:
    """Metadata-only record of one database tool attempt."""

    timestamp: str
    user_id: str
    tenant_id: str | None
    agent_id: str
    provider: str
    environment: str
    capability: str
    correlation_id: str
    duration_ms: int
    row_count: int
    truncated: bool
    outcome: str
    error_category: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


AUDIT_EVENT_FIELDS = frozenset(f.name for f in fields(DatabaseAuditEvent))


@runtime_checkable
class AuditSink(Protocol):
    def emit(self, event: DatabaseAuditEvent) -> None:
        ...


class LoggingAuditSink:
    """Default sink: one structured log line per attempt, metadata only."""

    def __init__(self, sink_logger: logging.Logger | None = None) -> None:
        self._logger = sink_logger or logger

    def emit(self, event: DatabaseAuditEvent) -> None:
        payload = json.dumps(event.to_dict(), sort_keys=True)
        level = logging.WARNING if event.outcome in (OUTCOME_DENIED, OUTCOME_ERROR) else logging.INFO
        self._logger.log(level, "database_tool_attempt %s", payload)


# ---------------------------------------------------------------------------
# Subject and decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatabaseSubject:
    """Everything the authorizer may consider, resolved server-side."""

    user_id: str
    tenant_id: str | None
    agent_id: str
    grant: AgentDatabaseGrant
    environment: Environment
    token_group_ids: Sequence[str] = ()
    groups_overage: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "token_group_ids", tuple(str(group) for group in (self.token_group_ids or ()))
        )


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    correlation_id: str
    reason: DenialReason | None = None

    @property
    def error_category(self) -> str | None:
        return self.reason.value if self.reason else None


def subject_from_user(user: Any, *, agent_id: str, grant: AgentDatabaseGrant) -> DatabaseSubject:
    """Build a subject from the authenticated user without trusting model input."""
    return DatabaseSubject(
        user_id=str(getattr(user, "user_id", "") or ""),
        tenant_id=getattr(user, "tenant_id", None),
        agent_id=agent_id,
        grant=grant,
        environment=grant.environment,
        token_group_ids=tuple(getattr(user, "group_ids", ()) or ()),
        groups_overage=bool(getattr(user, "groups_overage", False)),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


# ---------------------------------------------------------------------------
# Authorizer
# ---------------------------------------------------------------------------


class DatabaseAuthorizer:
    """Decides database capability access and emits one audit event per attempt."""

    def __init__(
        self,
        *,
        allowed_tenant_ids: Iterable[str],
        resolver: GroupMembershipResolver | None = None,
        audit_sink: AuditSink | None = None,
        clock: Callable[[], datetime] | None = None,
        cache_ttl_seconds: int = MAX_MEMBERSHIP_CACHE_SECONDS,
    ) -> None:
        self._tenant_ids = frozenset(
            str(tenant).strip() for tenant in allowed_tenant_ids if str(tenant).strip()
        )
        self.resolver: GroupMembershipResolver = resolver or FailClosedGroupMembershipResolver()
        self._audit_sink: AuditSink = audit_sink or LoggingAuditSink()
        self._clock = clock or _utc_now
        self._cache_ttl_seconds = max(0, min(int(cache_ttl_seconds), MAX_MEMBERSHIP_CACHE_SECONDS))
        self._cache: dict[tuple[str, str], tuple[frozenset[str], datetime]] = {}

    @property
    def cache_ttl_seconds(self) -> int:
        return self._cache_ttl_seconds

    @property
    def allowed_tenant_ids(self) -> frozenset[str]:
        return self._tenant_ids

    def invalidate(self, *, user_id: str | None = None, tenant_id: str | None = None) -> None:
        """Drop cached membership so the next attempt re-resolves immediately."""
        if user_id is None and tenant_id is None:
            self._cache.clear()
            return
        for key in [
            key
            for key in self._cache
            if (tenant_id is None or key[0] == tenant_id) and (user_id is None or key[1] == user_id)
        ]:
            self._cache.pop(key, None)

    async def evaluate(self, subject: DatabaseSubject, capability: Capability) -> AuthorizationDecision:
        """Decide without auditing; callers that audit must emit exactly one event."""
        correlation_id = new_correlation_id()
        tenant_id = str(subject.tenant_id or "").strip()
        if not tenant_id or tenant_id not in self._tenant_ids:
            return AuthorizationDecision(False, correlation_id, DenialReason.TENANT_NOT_CONFIGURED)
        if not subject.grant.allows(capability):
            return AuthorizationDecision(False, correlation_id, DenialReason.CAPABILITY_NOT_GRANTED)
        if subject.environment is not subject.grant.environment:
            return AuthorizationDecision(False, correlation_id, DenialReason.ENVIRONMENT_MISMATCH)
        if not subject.grant.entitled_groups:
            return AuthorizationDecision(False, correlation_id, DenialReason.NOT_ENTITLED)
        if subject.token_group_ids and subject.grant.entitles_groups(subject.token_group_ids):
            return AuthorizationDecision(True, correlation_id)

        try:
            resolved = await self._resolve_groups(subject, tenant_id)
        except Exception as exc:  # noqa: BLE001 — any resolution failure denies
            logger.warning(
                "Group membership resolution failed for user=%s tenant=%s: %s",
                subject.user_id,
                tenant_id,
                type(exc).__name__,
            )
            return AuthorizationDecision(False, correlation_id, DenialReason.MEMBERSHIP_UNRESOLVED)
        if resolved is None:
            return AuthorizationDecision(False, correlation_id, DenialReason.MEMBERSHIP_UNRESOLVED)
        if subject.grant.entitles_groups(resolved):
            return AuthorizationDecision(True, correlation_id)
        return AuthorizationDecision(False, correlation_id, DenialReason.NOT_ENTITLED)

    async def authorize(
        self, subject: DatabaseSubject, capability: Capability
    ) -> AuthorizationDecision:
        """Evaluate one pre-execution attempt and emit exactly one audit event."""
        decision = await self.evaluate(subject, capability)
        self.emit_audit(
            subject,
            capability,
            correlation_id=decision.correlation_id,
            outcome=OUTCOME_ALLOWED if decision.allowed else OUTCOME_DENIED,
            error_category=decision.error_category,
        )
        return decision

    async def authorize_grant(self, subject: DatabaseSubject) -> bool:
        """Authorize every capability the grant carries; one event per capability."""
        allowed = False
        for capability in sorted(subject.grant.capabilities, key=lambda item: item.value):
            decision = await self.authorize(subject, capability)
            allowed = allowed or decision.allowed
        return allowed

    def emit_audit(
        self,
        subject: DatabaseSubject,
        capability: Capability,
        *,
        correlation_id: str,
        outcome: str,
        error_category: str | None = None,
        duration_ms: int = 0,
        row_count: int = 0,
        truncated: bool = False,
    ) -> None:
        event = DatabaseAuditEvent(
            timestamp=self._clock().isoformat(),
            user_id=subject.user_id,
            tenant_id=subject.tenant_id,
            agent_id=subject.agent_id,
            provider=subject.grant.provider_id.value,
            environment=subject.environment.value,
            capability=capability.value,
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            row_count=row_count,
            truncated=truncated,
            outcome=outcome,
            error_category=error_category,
        )
        try:
            self._audit_sink.emit(event)
        except Exception:  # noqa: BLE001 — auditing must not break the caller
            logger.exception("Database audit sink failed for correlation %s", correlation_id)

    def now(self) -> datetime:
        return self._clock()

    async def _resolve_groups(self, subject: DatabaseSubject, tenant_id: str) -> frozenset[str] | None:
        key = (tenant_id, subject.user_id)
        now = self._clock()
        cached = self._cache.get(key)
        if cached is not None and cached[1] > now:
            return cached[0]
        self._cache.pop(key, None)
        raw = await _maybe_await(
            self.resolver.resolve_transitive_group_ids(user_id=subject.user_id, tenant_id=tenant_id)
        )
        if raw is None:
            return None
        resolved = frozenset(str(group) for group in raw)
        if self._cache_ttl_seconds:
            self._cache[key] = (resolved, now + timedelta(seconds=self._cache_ttl_seconds))
        return resolved


# ---------------------------------------------------------------------------
# Per-invocation guard
# ---------------------------------------------------------------------------


def guard_database_tools(
    tools: Mapping[str, Any] | Iterable[Any],
    *,
    authorizer: DatabaseAuthorizer,
    subject: DatabaseSubject,
) -> Any:
    """Wrap provider-bound tools so membership is re-checked before each call."""
    if isinstance(tools, Mapping):
        return {
            name: _guard_tool(tool, name=name, authorizer=authorizer, subject=subject)
            for name, tool in tools.items()
        }
    return [
        _guard_tool(
            tool,
            name=str(getattr(tool, "__name__", "")),
            authorizer=authorizer,
            subject=subject,
        )
        for tool in tools
    ]


def _guard_tool(
    tool: Any,
    *,
    name: str,
    authorizer: DatabaseAuthorizer,
    subject: DatabaseSubject,
) -> Any:
    try:
        capability = Capability(name)
    except ValueError:
        return tool

    @functools.wraps(tool)
    async def guarded(*args: Any, **kwargs: Any) -> Any:
        decision = await authorizer.evaluate(subject, capability)
        if not decision.allowed:
            authorizer.emit_audit(
                subject,
                capability,
                correlation_id=decision.correlation_id,
                outcome=OUTCOME_DENIED,
                error_category=decision.error_category,
            )
            return _denied_payload(capability, subject, decision.correlation_id)

        started = authorizer.now()
        try:
            result = await tool(*args, **kwargs)
        except Exception:
            authorizer.emit_audit(
                subject,
                capability,
                correlation_id=decision.correlation_id,
                outcome=OUTCOME_ERROR,
                error_category=QueryStatus.QUERY_ERROR.value,
                duration_ms=_elapsed_ms(started, authorizer.now()),
            )
            raise
        status, row_count, truncated = _result_metadata(result)
        authorizer.emit_audit(
            subject,
            capability,
            correlation_id=decision.correlation_id,
            outcome=status,
            error_category=None if status == QueryStatus.SUCCESS.value else status,
            duration_ms=_elapsed_ms(started, authorizer.now()),
            row_count=row_count,
            truncated=truncated,
        )
        return result

    return guarded


def _elapsed_ms(started: datetime, ended: datetime) -> int:
    return max(0, int((ended - started).total_seconds() * 1000))


def _result_metadata(result: Any) -> tuple[str, int, bool]:
    if not isinstance(result, Mapping):
        return QueryStatus.SUCCESS.value, 0, False
    status = str(result.get("status") or QueryStatus.SUCCESS.value)
    raw_rows = result.get("row_count")
    if raw_rows is None:
        rows = result.get("rows") or result.get("objects") or []
        raw_rows = len(rows) if isinstance(rows, Sequence) else 0
    return status, int(raw_rows), bool(result.get("truncated", False))


def _denied_payload(
    capability: Capability, subject: DatabaseSubject, correlation_id: str
) -> dict[str, Any]:
    from database import SchemaDiscoveryResult

    error = AuthorizationError(DENIED_MESSAGE)
    if capability is Capability.DATABASE_SCHEMA:
        return SchemaDiscoveryResult(
            provider=subject.grant.provider_id,
            correlation_id=correlation_id,
            status=error.status,
            message=error.message,
        ).to_dict()
    return error.to_result(
        provider=subject.grant.provider_id, correlation_id=correlation_id
    ).to_dict()


__all__ = [
    "AUDIT_EVENT_FIELDS",
    "MAX_MEMBERSHIP_CACHE_SECONDS",
    "AuditSink",
    "AuthorizationDecision",
    "DatabaseAuditEvent",
    "DatabaseAuthorizer",
    "DatabaseSubject",
    "DenialReason",
    "FailClosedGroupMembershipResolver",
    "GroupMembershipResolver",
    "LoggingAuditSink",
    "MembershipResolutionError",
    "guard_database_tools",
    "subject_from_user",
]
