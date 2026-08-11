"""Offline tests for database entitlement authorization and metadata-only auditing."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from database import (
    AgentDatabaseGrant,
    Capability,
    ColumnMetadata,
    Environment,
    NormalizedType,
    ProviderId,
    QueryRequest,
    QueryResult,
    QueryStatus,
    SchemaDiscoveryResult,
    SchemaRequest,
    new_correlation_id,
)
from database_authorization import (
    AUDIT_EVENT_FIELDS,
    MAX_MEMBERSHIP_CACHE_SECONDS,
    DatabaseAuthorizer,
    DatabaseSubject,
    DenialReason,
    FailClosedGroupMembershipResolver,
    MembershipResolutionError,
    guard_database_tools,
)
from tools import build_database_tools

TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
ENTITLED_GROUP = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CHILD_GROUP = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
OTHER_GROUP = "cccccccc-cccc-cccc-cccc-cccccccccccc"

SECRET_SQL = "SELECT super_secret_column FROM sales.orders"
SECRET_PARAMETER = "super-secret-parameter-value"
SECRET_CELL = "super-secret-result-cell"

EXCLUDED_AUDIT_KEYS = {
    "sql",
    "sql_text",
    "sql_hash",
    "query",
    "statement",
    "parameters",
    "parameter_hash",
    "rows",
    "columns",
    "result",
    "credential",
    "credentials",
    "password",
    "token",
    "connection_string",
    "host",
    "port",
    "database",
    "driver_error",
    "exception",
    "stack",
}


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


class RecordingSink:
    def __init__(self) -> None:
        self.events: list = []

    def emit(self, event) -> None:
        self.events.append(event)

    @property
    def payloads(self) -> list[dict]:
        return [event.to_dict() for event in self.events]


class FakeGraphResolver:
    """Expands a nested group graph the way transitive Graph resolution would."""

    def __init__(self, direct: dict[str, list[str]], parents: dict[str, list[str]] | None = None) -> None:
        self.direct = direct
        self.parents = parents or {}
        self.calls = 0

    def resolve_transitive_group_ids(self, *, user_id: str, tenant_id: str):
        self.calls += 1
        seen: set[str] = set()
        pending = list(self.direct.get(user_id, []))
        while pending:
            group = pending.pop()
            if group in seen:
                continue
            seen.add(group)
            pending.extend(self.parents.get(group, []))
        return sorted(seen)


class ExplodingResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_transitive_group_ids(self, *, user_id: str, tenant_id: str):
        self.calls += 1
        raise RuntimeError("graph endpoint unavailable")


class AsyncResolver:
    def __init__(self, groups: list[str]) -> None:
        self.groups = groups
        self.calls = 0

    async def resolve_transitive_group_ids(self, *, user_id: str, tenant_id: str):
        self.calls += 1
        return list(self.groups)


class FakeProvider:
    def __init__(self, provider_id: ProviderId = ProviderId.HANA) -> None:
        self.provider_id = provider_id
        self.query_calls = 0
        self.schema_calls = 0

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def discover_schema(self, request: SchemaRequest) -> SchemaDiscoveryResult:
        self.schema_calls += 1
        return SchemaDiscoveryResult(
            provider=self.provider_id,
            correlation_id=new_correlation_id(),
            truncated=True,
        )

    async def execute_query(self, request: QueryRequest) -> QueryResult:
        self.query_calls += 1
        return QueryResult(
            provider=self.provider_id,
            correlation_id=new_correlation_id(),
            columns=[ColumnMetadata("secret", NormalizedType.STRING)],
            rows=[[SECRET_CELL], [SECRET_CELL]],
            truncated=True,
        )


def make_grant(
    *,
    groups: list[str] | None = None,
    environment: Environment = Environment.PRODUCTION,
    capabilities: tuple[Capability, ...] = (Capability.DATABASE_QUERY, Capability.DATABASE_SCHEMA),
) -> AgentDatabaseGrant:
    return AgentDatabaseGrant(
        provider_id=ProviderId.HANA,
        capabilities=capabilities,
        entitled_groups=[ENTITLED_GROUP] if groups is None else groups,
        environment=environment,
    )


def make_subject(
    *,
    tenant_id: str | None = TENANT,
    grant: AgentDatabaseGrant | None = None,
    token_group_ids: tuple[str, ...] = (),
    groups_overage: bool = False,
    environment: Environment | None = None,
) -> DatabaseSubject:
    resolved_grant = grant or make_grant()
    return DatabaseSubject(
        user_id="user-1",
        tenant_id=tenant_id,
        agent_id="hana-analyst",
        grant=resolved_grant,
        environment=environment or resolved_grant.environment,
        token_group_ids=token_group_ids,
        groups_overage=groups_overage,
    )


def make_authorizer(
    *,
    resolver=None,
    sink=None,
    clock=None,
    tenants: tuple[str, ...] = (TENANT,),
    cache_ttl_seconds: int = MAX_MEMBERSHIP_CACHE_SECONDS,
) -> DatabaseAuthorizer:
    return DatabaseAuthorizer(
        allowed_tenant_ids=tenants,
        resolver=resolver,
        audit_sink=sink,
        clock=clock,
        cache_ttl_seconds=cache_ttl_seconds,
    )


# ---------------------------------------------------------------------------
# Tenant scoping
# ---------------------------------------------------------------------------


def test_configured_tenant_with_direct_membership_is_allowed():
    sink = RecordingSink()
    resolver = FakeGraphResolver({})
    authorizer = make_authorizer(resolver=resolver, sink=sink)
    subject = make_subject(token_group_ids=(ENTITLED_GROUP,))

    decision = asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))

    assert decision.allowed is True
    assert decision.reason is None
    assert resolver.calls == 0
    assert [event.outcome for event in sink.events] == ["allowed"]


def test_wrong_tenant_is_denied_even_with_entitled_group_claim():
    sink = RecordingSink()
    resolver = FakeGraphResolver({"user-1": [ENTITLED_GROUP]})
    authorizer = make_authorizer(resolver=resolver, sink=sink)
    subject = make_subject(tenant_id=OTHER_TENANT, token_group_ids=(ENTITLED_GROUP,))

    decision = asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))

    assert decision.allowed is False
    assert decision.reason is DenialReason.TENANT_NOT_CONFIGURED
    assert resolver.calls == 0
    assert sink.events[0].outcome == "denied"
    assert sink.events[0].error_category == DenialReason.TENANT_NOT_CONFIGURED.value


def test_missing_tenant_is_denied():
    authorizer = make_authorizer(resolver=FakeGraphResolver({}))
    decision = asyncio.run(
        authorizer.authorize(make_subject(tenant_id=None, token_group_ids=(ENTITLED_GROUP,)), Capability.DATABASE_QUERY)
    )
    assert decision.allowed is False
    assert decision.reason is DenialReason.TENANT_NOT_CONFIGURED


# ---------------------------------------------------------------------------
# Membership resolution
# ---------------------------------------------------------------------------


def test_transitive_nested_membership_is_allowed():
    resolver = FakeGraphResolver(
        {"user-1": [CHILD_GROUP]},
        parents={CHILD_GROUP: [ENTITLED_GROUP]},
    )
    authorizer = make_authorizer(resolver=resolver)
    subject = make_subject(token_group_ids=())

    decision = asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))

    assert decision.allowed is True
    assert resolver.calls == 1


def test_group_claim_overage_triggers_resolver():
    resolver = FakeGraphResolver({"user-1": [ENTITLED_GROUP]})
    authorizer = make_authorizer(resolver=resolver)
    subject = make_subject(token_group_ids=(OTHER_GROUP,), groups_overage=True)

    decision = asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))

    assert decision.allowed is True
    assert resolver.calls == 1


def test_async_resolver_is_supported():
    resolver = AsyncResolver([ENTITLED_GROUP])
    authorizer = make_authorizer(resolver=resolver)

    decision = asyncio.run(authorizer.authorize(make_subject(), Capability.DATABASE_QUERY))

    assert decision.allowed is True
    assert resolver.calls == 1


def test_resolver_error_fails_closed():
    resolver = ExplodingResolver()
    sink = RecordingSink()
    authorizer = make_authorizer(resolver=resolver, sink=sink)

    decision = asyncio.run(authorizer.authorize(make_subject(), Capability.DATABASE_QUERY))

    assert decision.allowed is False
    assert decision.reason is DenialReason.MEMBERSHIP_UNRESOLVED
    assert resolver.calls == 1
    assert sink.events[0].error_category == DenialReason.MEMBERSHIP_UNRESOLVED.value
    assert "graph endpoint unavailable" not in json.dumps(sink.payloads)


def test_default_resolver_is_fail_closed():
    authorizer = DatabaseAuthorizer(allowed_tenant_ids=(TENANT,))
    assert isinstance(authorizer.resolver, FailClosedGroupMembershipResolver)

    decision = asyncio.run(authorizer.authorize(make_subject(), Capability.DATABASE_QUERY))

    assert decision.allowed is False
    assert decision.reason is DenialReason.MEMBERSHIP_UNRESOLVED
    with pytest.raises(MembershipResolutionError):
        FailClosedGroupMembershipResolver().resolve_transitive_group_ids(user_id="user-1", tenant_id=TENANT)


def test_nonmember_is_denied():
    resolver = FakeGraphResolver({"user-1": [OTHER_GROUP]})
    authorizer = make_authorizer(resolver=resolver)

    decision = asyncio.run(authorizer.authorize(make_subject(), Capability.DATABASE_QUERY))

    assert decision.allowed is False
    assert decision.reason is DenialReason.NOT_ENTITLED


def test_empty_entitled_groups_allows_nobody():
    resolver = FakeGraphResolver({"user-1": [ENTITLED_GROUP, OTHER_GROUP]})
    authorizer = make_authorizer(resolver=resolver)
    subject = make_subject(grant=make_grant(groups=[]), token_group_ids=(ENTITLED_GROUP,))

    decision = asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))

    assert decision.allowed is False
    assert decision.reason is DenialReason.NOT_ENTITLED


def test_capability_outside_grant_is_denied():
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [ENTITLED_GROUP]}))
    subject = make_subject(grant=make_grant(capabilities=(Capability.DATABASE_SCHEMA,)))

    decision = asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))

    assert decision.allowed is False
    assert decision.reason is DenialReason.CAPABILITY_NOT_GRANTED


def test_environment_mismatch_is_denied():
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [ENTITLED_GROUP]}))
    subject = make_subject(
        grant=make_grant(environment=Environment.PRODUCTION),
        environment=Environment.DEVELOPMENT,
        token_group_ids=(ENTITLED_GROUP,),
    )

    decision = asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))

    assert decision.allowed is False
    assert decision.reason is DenialReason.ENVIRONMENT_MISMATCH


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


def test_cache_ttl_is_clamped_to_five_minutes():
    authorizer = make_authorizer(resolver=FakeGraphResolver({}), cache_ttl_seconds=3600)
    assert authorizer.cache_ttl_seconds == MAX_MEMBERSHIP_CACHE_SECONDS == 300


def test_cache_hit_within_ttl_skips_resolver():
    clock = FakeClock()
    resolver = FakeGraphResolver({"user-1": [ENTITLED_GROUP]})
    authorizer = make_authorizer(resolver=resolver, clock=clock)
    subject = make_subject()

    assert asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY)).allowed is True
    clock.advance(299)
    assert asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY)).allowed is True

    assert resolver.calls == 1


def test_cache_expiry_forces_reevaluation():
    clock = FakeClock()
    resolver = FakeGraphResolver({"user-1": [ENTITLED_GROUP]})
    authorizer = make_authorizer(resolver=resolver, clock=clock)
    subject = make_subject()

    asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))
    clock.advance(301)
    asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))

    assert resolver.calls == 2


def test_revoked_membership_is_denied_after_cache_expiry():
    clock = FakeClock()
    resolver = FakeGraphResolver({"user-1": [ENTITLED_GROUP]})
    authorizer = make_authorizer(resolver=resolver, clock=clock)
    subject = make_subject()

    assert asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY)).allowed is True

    resolver.direct["user-1"] = []
    clock.advance(301)

    decision = asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))
    assert decision.allowed is False
    assert decision.reason is DenialReason.NOT_ENTITLED


def test_invalidate_forces_immediate_reevaluation():
    clock = FakeClock()
    resolver = FakeGraphResolver({"user-1": [ENTITLED_GROUP]})
    authorizer = make_authorizer(resolver=resolver, clock=clock)
    subject = make_subject()

    asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY))
    resolver.direct["user-1"] = []
    authorizer.invalidate(user_id="user-1", tenant_id=TENANT)

    assert asyncio.run(authorizer.authorize(subject, Capability.DATABASE_QUERY)).allowed is False


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------


def _assert_metadata_only(payload: dict) -> None:
    assert set(payload) == AUDIT_EVENT_FIELDS
    assert not set(payload) & EXCLUDED_AUDIT_KEYS
    serialized = json.dumps(payload, default=str)
    for secret in (SECRET_SQL, SECRET_PARAMETER, SECRET_CELL, "super_secret_column"):
        assert secret not in serialized


def test_pre_execution_audit_event_has_exact_metadata_fields():
    sink = RecordingSink()
    clock = FakeClock()
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [ENTITLED_GROUP]}), sink=sink, clock=clock)

    asyncio.run(authorizer.authorize(make_subject(), Capability.DATABASE_SCHEMA))

    assert len(sink.events) == 1
    payload = sink.payloads[0]
    _assert_metadata_only(payload)
    assert payload["timestamp"] == clock.now.isoformat()
    assert payload["user_id"] == "user-1"
    assert payload["tenant_id"] == TENANT
    assert payload["agent_id"] == "hana-analyst"
    assert payload["provider"] == ProviderId.HANA.value
    assert payload["environment"] == Environment.PRODUCTION.value
    assert payload["capability"] == Capability.DATABASE_SCHEMA.value
    assert payload["correlation_id"]
    assert payload["duration_ms"] == 0
    assert payload["row_count"] == 0
    assert payload["truncated"] is False
    assert payload["outcome"] == "allowed"
    assert payload["error_category"] is None


def test_denied_audit_event_uses_zero_rows_and_untruncated():
    sink = RecordingSink()
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [OTHER_GROUP]}), sink=sink)

    asyncio.run(authorizer.authorize(make_subject(), Capability.DATABASE_QUERY))

    assert len(sink.events) == 1
    payload = sink.payloads[0]
    _assert_metadata_only(payload)
    assert payload["outcome"] == "denied"
    assert payload["error_category"] == DenialReason.NOT_ENTITLED.value
    assert payload["row_count"] == 0
    assert payload["truncated"] is False


def test_denied_tenant_never_leaks_unconfigured_tenant_details():
    sink = RecordingSink()
    authorizer = make_authorizer(resolver=FakeGraphResolver({}), sink=sink)

    asyncio.run(authorizer.authorize(make_subject(tenant_id=OTHER_TENANT), Capability.DATABASE_QUERY))

    payload = sink.payloads[0]
    _assert_metadata_only(payload)
    assert payload["tenant_id"] == OTHER_TENANT


# ---------------------------------------------------------------------------
# Guarded tool invocation
# ---------------------------------------------------------------------------


def _guarded_tools(authorizer, subject, provider=None):
    provider = provider or FakeProvider()
    tools = build_database_tools(provider, subject.grant)
    return provider, guard_database_tools(tools, authorizer=authorizer, subject=subject)


def test_guarded_query_runs_and_emits_one_metadata_only_event():
    sink = RecordingSink()
    clock = FakeClock()
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [ENTITLED_GROUP]}), sink=sink, clock=clock)
    subject = make_subject()
    provider, tools = _guarded_tools(authorizer, subject)

    result = asyncio.run(tools["database_query"](SECRET_SQL, [SECRET_PARAMETER]))

    assert result["status"] == QueryStatus.SUCCESS.value
    assert provider.query_calls == 1
    assert len(sink.events) == 1
    payload = sink.payloads[0]
    _assert_metadata_only(payload)
    assert payload["outcome"] == QueryStatus.SUCCESS.value
    assert payload["error_category"] is None
    assert payload["row_count"] == 2
    assert payload["truncated"] is True
    assert payload["capability"] == Capability.DATABASE_QUERY.value


def test_guarded_tools_preserve_model_facing_names_and_signature():
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [ENTITLED_GROUP]}))
    subject = make_subject()
    _, tools = _guarded_tools(authorizer, subject)

    assert set(tools) == {"database_query", "database_schema"}
    assert tools["database_query"].__name__ == "database_query"
    import inspect

    assert list(inspect.signature(tools["database_query"]).parameters) == [
        "sql",
        "parameters",
        "continuation",
    ]


def test_guarded_query_denies_nonmember_without_touching_provider():
    sink = RecordingSink()
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [OTHER_GROUP]}), sink=sink)
    subject = make_subject()
    provider, tools = _guarded_tools(authorizer, subject)

    result = asyncio.run(tools["database_query"](SECRET_SQL, [SECRET_PARAMETER]))

    assert result["status"] == QueryStatus.AUTHORIZATION_ERROR.value
    assert result["rows"] == []
    assert provider.query_calls == 0
    assert len(sink.events) == 1
    _assert_metadata_only(sink.payloads[0])
    assert sink.payloads[0]["outcome"] == "denied"


def test_guarded_schema_denial_returns_schema_shaped_error():
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [OTHER_GROUP]}))
    subject = make_subject()
    provider, tools = _guarded_tools(authorizer, subject)

    result = asyncio.run(tools["database_schema"]())

    assert result["status"] == QueryStatus.AUTHORIZATION_ERROR.value
    assert result["objects"] == []
    assert provider.schema_calls == 0


def test_existing_session_is_denied_after_membership_revocation():
    sink = RecordingSink()
    clock = FakeClock()
    resolver = FakeGraphResolver({"user-1": [ENTITLED_GROUP]})
    authorizer = make_authorizer(resolver=resolver, sink=sink, clock=clock)
    subject = make_subject()
    provider, tools = _guarded_tools(authorizer, subject)

    first = asyncio.run(tools["database_query"]("SELECT 1 FROM sales.orders"))
    assert first["status"] == QueryStatus.SUCCESS.value

    resolver.direct["user-1"] = []
    clock.advance(301)

    second = asyncio.run(tools["database_query"]("SELECT 1 FROM sales.orders"))
    assert second["status"] == QueryStatus.AUTHORIZATION_ERROR.value
    assert provider.query_calls == 1
    assert [event.outcome for event in sink.events] == [QueryStatus.SUCCESS.value, "denied"]


def test_existing_session_is_denied_when_resolver_becomes_unavailable():
    clock = FakeClock()
    resolver = FakeGraphResolver({"user-1": [ENTITLED_GROUP]})
    authorizer = make_authorizer(resolver=resolver, clock=clock)
    subject = make_subject()
    provider, tools = _guarded_tools(authorizer, subject)

    assert asyncio.run(tools["database_query"]("SELECT 1 FROM sales.orders"))["status"] == QueryStatus.SUCCESS.value

    authorizer.resolver = ExplodingResolver()
    clock.advance(301)

    result = asyncio.run(tools["database_query"]("SELECT 1 FROM sales.orders"))
    assert result["status"] == QueryStatus.AUTHORIZATION_ERROR.value
    assert provider.query_calls == 1


# ---------------------------------------------------------------------------
# Session orchestration boundary
# ---------------------------------------------------------------------------


class FakeUser:
    def __init__(self, *, tenant_id: str | None = TENANT, group_ids: tuple[str, ...] = ()) -> None:
        self.user_id = "user-1"
        self.username = "user-1@example.test"
        self.tenant_id = tenant_id
        self.group_ids = group_ids
        self.groups_overage = False


def _session_context(**overrides):
    from app_context import DatabaseProviderRegistry, build_tool_instances
    from session_orchestration import SessionContext

    provider = overrides.pop("provider", None) or FakeProvider()
    registry = DatabaseProviderRegistry([provider])

    def build(tool_names, *, session_id, user_id=None, database_grant=None):
        return build_tool_instances(
            tool_names,
            session_id=session_id,
            user_id=user_id,
            database_grant=database_grant,
            database_registry=registry,
        )

    ctx = SessionContext(
        sessions={},
        session_data_cls=object,
        build_tool_instances=build,
        build_user_profile_context=lambda profile: "",
        **overrides,
    )
    return provider, ctx


def _resolve_database_tools(ctx, user):
    from session_orchestration import _authorized_database_tools

    return asyncio.run(
        _authorized_database_tools(
            ctx,
            user=user,
            agent_id="hana-analyst",
            session_id="session-1",
            logger=logging.getLogger("test"),
        )
    )


def test_session_without_database_wiring_is_unchanged():
    _, ctx = _session_context()
    assert ctx.database_authorizer is None
    assert ctx.database_grant_resolver is None
    assert _resolve_database_tools(ctx, FakeUser()) == []


def test_session_exposes_guarded_tools_to_entitled_user():
    sink = RecordingSink()
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [ENTITLED_GROUP]}), sink=sink)
    grant = make_grant()
    provider, ctx = _session_context(
        database_authorizer=authorizer,
        database_grant_resolver=lambda user, agent_id: grant,
    )

    tools = _resolve_database_tools(ctx, FakeUser())

    assert sorted(tool.__name__ for tool in tools) == ["database_query", "database_schema"]
    assert [event.outcome for event in sink.events] == ["allowed", "allowed"]
    assert {event.capability for event in sink.events} == {
        Capability.DATABASE_QUERY.value,
        Capability.DATABASE_SCHEMA.value,
    }
    for payload in sink.payloads:
        _assert_metadata_only(payload)

    by_name = {tool.__name__: tool for tool in tools}
    assert asyncio.run(by_name["database_query"]("SELECT 1 FROM sales.orders"))["status"] == (
        QueryStatus.SUCCESS.value
    )
    assert provider.query_calls == 1


def test_session_withholds_tools_from_unentitled_user_and_audits_denial():
    sink = RecordingSink()
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [OTHER_GROUP]}), sink=sink)
    grant = make_grant()
    provider, ctx = _session_context(
        database_authorizer=authorizer,
        database_grant_resolver=lambda user, agent_id: grant,
    )

    assert _resolve_database_tools(ctx, FakeUser()) == []
    assert provider.query_calls == 0
    assert [event.outcome for event in sink.events] == ["denied", "denied"]
    for payload in sink.payloads:
        _assert_metadata_only(payload)
        assert payload["row_count"] == 0
        assert payload["truncated"] is False


def test_session_withholds_tools_from_unconfigured_tenant():
    sink = RecordingSink()
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [ENTITLED_GROUP]}), sink=sink)
    grant = make_grant()
    _, ctx = _session_context(
        database_authorizer=authorizer,
        database_grant_resolver=lambda user, agent_id: grant,
    )

    assert _resolve_database_tools(ctx, FakeUser(tenant_id=OTHER_TENANT)) == []
    assert {event.error_category for event in sink.events} == {
        DenialReason.TENANT_NOT_CONFIGURED.value
    }


def test_session_without_grant_exposes_no_database_tools():
    sink = RecordingSink()
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [ENTITLED_GROUP]}), sink=sink)
    _, ctx = _session_context(
        database_authorizer=authorizer,
        database_grant_resolver=lambda user, agent_id: None,
    )

    assert _resolve_database_tools(ctx, FakeUser()) == []
    assert sink.events == []


def test_session_grant_resolver_failure_fails_closed():
    sink = RecordingSink()
    authorizer = make_authorizer(resolver=FakeGraphResolver({"user-1": [ENTITLED_GROUP]}), sink=sink)

    def boom(user, agent_id):
        raise RuntimeError("grant store unavailable")

    _, ctx = _session_context(database_authorizer=authorizer, database_grant_resolver=boom)

    assert _resolve_database_tools(ctx, FakeUser()) == []
    assert sink.events == []
