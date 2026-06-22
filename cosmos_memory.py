"""Azure Cosmos DB memory layer for agent chat history and conversation index.

Provides two things:

1. ``get_history_provider()`` — the Agent Framework ``HistoryProvider`` used by
   ``agent_factory`` for durable per-session message memory. Returns a
   ``CosmosHistoryProvider``; Cosmos is required (the emulator locally, a real
   account when deployed) and there is no runtime fallback.

2. ``get_conversation_repository()`` — a per-user conversation *index* (the data
   that powers the left chat pane and enforces ownership), backed by a Cosmos
   container partitioned by ``/user_id``.

Tests run against the emulator; where they need a double they monkeypatch the
module-level ``_history_provider`` / ``_conversation_repo`` singletons (see
``tests/_doubles.py``).

Credentials: a Cosmos account key (``AZURE_COSMOS_KEY``) is used for local /
emulator development only; production uses ``DefaultAzureCredential`` (managed
identity) and Azure Government endpoints. Keys are never logged.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def cosmos_config_summary() -> dict[str, str]:
    """Non-secret Cosmos settings for startup logging (never the account key)."""
    endpoint = (os.getenv("AZURE_COSMOS_ENDPOINT") or "").strip()
    host = urlsplit(endpoint).hostname or ""
    has_key = bool((os.getenv("AZURE_COSMOS_KEY") or "").strip())
    return {
        "endpoint": endpoint,
        "database": (os.getenv("AZURE_COSMOS_DATABASE_NAME") or "agent-memory").strip(),
        "messages_container": (os.getenv("AZURE_COSMOS_CONTAINER_NAME") or "chat-history").strip(),
        "conversations_container": (os.getenv("AZURE_COSMOS_CONVERSATIONS_CONTAINER") or "conversations").strip(),
        "auth": "key" if has_key or host in ("localhost", "127.0.0.1") else "managed-identity",
    }


# Public, fixed master key the Azure Cosmos DB Emulator accepts (NOT a secret —
# Microsoft documents it). The emulator rejects AAD tokens, so the local client
# uses this key unless AZURE_COSMOS_KEY is set.
_EMULATOR_WELL_KNOWN_KEY = (
    "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
)


# ---------------------------------------------------------------------------
# Conversation index record
# ---------------------------------------------------------------------------

@dataclass
class ConversationRecord:
    """One conversation-index entry (partitioned by ``user_id`` in Cosmos)."""

    id: str
    user_id: str
    profile_id: str
    profile_name: str
    title: str = ""
    created_at: str = ""
    last_activity_at: str = ""
    custom_agent_id: str | None = None
    used_builtin_override: bool = False
    base_profile_id: str | None = None
    override_updated_at: str | None = None

    def to_doc(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "title": self.title,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "custom_agent_id": self.custom_agent_id,
            "used_builtin_override": self.used_builtin_override,
            "base_profile_id": self.base_profile_id,
            "override_updated_at": self.override_updated_at,
            "doc_type": "conversation",
            "schema_version": 1,
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ConversationRecord":
        return cls(
            id=str(doc["id"]),
            user_id=str(doc.get("user_id", "")),
            profile_id=str(doc.get("profile_id", "")),
            profile_name=str(doc.get("profile_name", "")),
            title=str(doc.get("title", "")),
            created_at=str(doc.get("created_at", "")),
            last_activity_at=str(doc.get("last_activity_at", "")),
            custom_agent_id=doc.get("custom_agent_id"),
            used_builtin_override=bool(doc.get("used_builtin_override", False)),
            base_profile_id=doc.get("base_profile_id"),
            override_updated_at=doc.get("override_updated_at"),
        )

    def to_wire(self) -> dict[str, Any]:
        """Shape consumed by the frontend ``ConversationIndexEntry``."""
        return {
            "id": self.id,
            "profileId": self.profile_id,
            "profileName": self.profile_name,
            "description": self.title,
            "createdAt": self.created_at,
            "lastActivityAt": self.last_activity_at,
            "customAgentId": self.custom_agent_id,
            "usedBuiltInOverride": self.used_builtin_override,
            "baseProfileId": self.base_profile_id,
            "overrideUpdatedAt": self.override_updated_at,
        }


# ---------------------------------------------------------------------------
# Conversation index repository
# ---------------------------------------------------------------------------

class ConversationIndexRepository(Protocol):
    """Per-user conversation index. All methods are partition-scoped by user_id."""

    async def create(
        self,
        user_id: str,
        conversation_id: str,
        profile_id: str,
        profile_name: str,
        *,
        custom_agent_id: str | None = None,
        used_builtin_override: bool = False,
        base_profile_id: str | None = None,
        override_updated_at: str | None = None,
    ) -> ConversationRecord: ...

    async def list_for_user(
        self, user_id: str, *, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[ConversationRecord], str | None]: ...

    async def get_owned(self, user_id: str, conversation_id: str) -> ConversationRecord | None: ...

    async def touch(self, user_id: str, conversation_id: str, *, title: str | None = None) -> None: ...

    async def delete(self, user_id: str, conversation_id: str) -> bool: ...


class _CosmosContainer:
    """Base for the Cosmos repositories: one lazily-created container bound to a
    single partition key.

    Owns the bootstrap each repository used to repeat by hand (create database +
    container on first use). Subclasses pass their partition path (and optional
    per-item TTL) and add only the queries that actually differ.
    """

    def __init__(
        self,
        client: Any,
        database_name: str,
        container_name: str,
        *,
        partition_key: str,
        default_ttl: int | None = None,
    ) -> None:
        self._client = client
        self._database_name = database_name
        self._container_name = container_name
        self._partition_key = partition_key
        self._default_ttl = default_ttl
        self._container: Any = None

    async def _get_container(self) -> Any:
        if self._container is None:
            from azure.cosmos import PartitionKey

            database = await self._client.create_database_if_not_exists(self._database_name)
            kwargs: dict[str, Any] = {
                "id": self._container_name,
                "partition_key": PartitionKey(path=self._partition_key),
            }
            if self._default_ttl is not None:
                kwargs["default_ttl"] = self._default_ttl
            self._container = await database.create_container_if_not_exists(**kwargs)
        return self._container


class CosmosConversationRepository(_CosmosContainer):
    """Cosmos-backed conversation index, partitioned by ``/user_id``."""

    def __init__(self, client: Any, database_name: str, container_name: str) -> None:
        super().__init__(client, database_name, container_name, partition_key="/user_id")

    async def create(
        self,
        user_id: str,
        conversation_id: str,
        profile_id: str,
        profile_name: str,
        *,
        custom_agent_id: str | None = None,
        used_builtin_override: bool = False,
        base_profile_id: str | None = None,
        override_updated_at: str | None = None,
    ) -> ConversationRecord:
        now = datetime.now(timezone.utc).isoformat()
        record = ConversationRecord(
            id=conversation_id,
            user_id=user_id,
            profile_id=profile_id,
            profile_name=profile_name,
            title="",
            created_at=now,
            last_activity_at=now,
            custom_agent_id=custom_agent_id,
            used_builtin_override=used_builtin_override,
            base_profile_id=base_profile_id,
            override_updated_at=override_updated_at,
        )
        container = await self._get_container()
        await container.upsert_item(record.to_doc())
        return record

    async def list_for_user(
        self, user_id: str, *, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[ConversationRecord], str | None]:
        container = await self._get_container()
        query = (
            "SELECT * FROM c WHERE c.user_id = @uid "
            "ORDER BY c.last_activity_at DESC"
        )
        parameters = [{"name": "@uid", "value": user_id}]
        records: list[ConversationRecord] = []
        items = container.query_items(
            query=query,
            parameters=parameters,
            partition_key=user_id,
        )
        async for item in items:
            records.append(ConversationRecord.from_doc(item))
            if len(records) >= max(0, limit):
                break
        return records, None

    async def get_owned(self, user_id: str, conversation_id: str) -> ConversationRecord | None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        try:
            item = await container.read_item(item=conversation_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            return None
        return ConversationRecord.from_doc(item)

    async def touch(self, user_id: str, conversation_id: str, *, title: str | None = None) -> None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        try:
            item = await container.read_item(item=conversation_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            return
        item["last_activity_at"] = datetime.now(timezone.utc).isoformat()
        if title and not item.get("title"):
            item["title"] = title
        await container.upsert_item(item)

    async def delete(self, user_id: str, conversation_id: str) -> bool:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        try:
            await container.delete_item(item=conversation_id, partition_key=user_id)
            return True
        except CosmosResourceNotFoundError:
            return False


# ---------------------------------------------------------------------------
# Autonomous run audit record (partitioned by ``directive_id`` in Cosmos)
# ---------------------------------------------------------------------------

# Cap the stored response text so a single run record stays well under the 2 MB
# Cosmos item limit. The full response always remains in the chat-history container.
MAX_RUN_RESPONSE_CHARS = 8000


@dataclass
class AutonomousRunRecord:
    """One execution of a directive — the durable, tamper-evident audit record.

    Contains NO secrets: webhook URLs/keys are referenced by env-var name in
    config and are never copied into a run record.
    """

    id: str
    directive_id: str
    profile_id: str
    session_id: str
    status: str  # "success" | "failure"
    started_at: str
    finished_at: str
    response_text: str = ""
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    notify_status: str = "skipped"  # "logged" | "delivered" | "skipped" | "failed"
    notify_error: str | None = None
    trigger: str = "manual"  # "timer" | "manual"

    def to_doc(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "directive_id": self.directive_id,
            "profile_id": self.profile_id,
            "session_id": self.session_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "response_text": self.response_text[:MAX_RUN_RESPONSE_CHARS],
            "tool_events": self.tool_events,
            "usage": self.usage,
            "error": self.error,
            "notify_status": self.notify_status,
            "notify_error": self.notify_error,
            "trigger": self.trigger,
            "doc_type": "autonomous_run",
            "schema_version": 1,
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "AutonomousRunRecord":
        return cls(
            id=str(doc["id"]),
            directive_id=str(doc.get("directive_id", "")),
            profile_id=str(doc.get("profile_id", "")),
            session_id=str(doc.get("session_id", "")),
            status=str(doc.get("status", "")),
            started_at=str(doc.get("started_at", "")),
            finished_at=str(doc.get("finished_at", "")),
            response_text=str(doc.get("response_text", "")),
            tool_events=list(doc.get("tool_events") or []),
            usage=dict(doc.get("usage") or {}),
            error=doc.get("error"),
            notify_status=str(doc.get("notify_status", "skipped")),
            notify_error=doc.get("notify_error"),
            trigger=str(doc.get("trigger", "manual")),
        )

    def to_wire(self) -> dict[str, Any]:
        """camelCase shape consumed by the frontend ``AutonomousRun`` (no secrets)."""
        return {
            "id": self.id,
            "directiveId": self.directive_id,
            "profileId": self.profile_id,
            "sessionId": self.session_id,
            "status": self.status,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "responseText": self.response_text[:MAX_RUN_RESPONSE_CHARS],
            "toolEvents": self.tool_events,
            "usage": self.usage,
            "error": self.error,
            "notifyStatus": self.notify_status,
            "notifyError": self.notify_error,
            "trigger": self.trigger,
        }


class CosmosAutonomousRunRepository(_CosmosContainer):
    """Cosmos-backed autonomous run audit log, partitioned by ``/directive_id``."""

    def __init__(self, client: Any, database_name: str, container_name: str) -> None:
        super().__init__(client, database_name, container_name, partition_key="/directive_id")

    async def create_run(self, record: AutonomousRunRecord) -> AutonomousRunRecord:
        container = await self._get_container()
        await container.upsert_item(record.to_doc())
        return record

    async def list_runs(
        self, *, limit: int = 50, directive_id: str | None = None
    ) -> list[AutonomousRunRecord]:
        container = await self._get_container()
        limit = max(0, min(limit, 200))
        if directive_id:
            query = (
                "SELECT * FROM c WHERE c.directive_id = @did "
                "ORDER BY c.started_at DESC"
            )
            items = container.query_items(
                query=query,
                parameters=[{"name": "@did", "value": directive_id}],
                partition_key=directive_id,
            )
        else:
            # Bounded cross-partition recency query (low volume — one doc per cycle).
            query = "SELECT * FROM c ORDER BY c.started_at DESC"
            items = container.query_items(query=query)
        records: list[AutonomousRunRecord] = []
        async for item in items:
            records.append(AutonomousRunRecord.from_doc(item))
            if len(records) >= limit:
                break
        return records

    async def get_run(self, run_id: str, directive_id: str) -> AutonomousRunRecord | None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        try:
            item = await container.read_item(item=run_id, partition_key=directive_id)
        except CosmosResourceNotFoundError:
            return None
        return AutonomousRunRecord.from_doc(item)


class CosmosAutonomousLeaseRepository(_CosmosContainer):
    """Cosmos-backed at-most-once scheduler lease, partitioned by ``/directive_id``.

    The atomic ``create_item`` on the ``{directive_id}:{slot}`` id IS the lock: the
    first writer of a slot wins; a ``CosmosResourceExistsError`` means another
    instance (or an earlier tick) already claimed it. Lease docs carry a per-item
    TTL so they self-expire (the container is created with ``default_ttl = -1``).
    """

    def __init__(self, client: Any, database_name: str, container_name: str) -> None:
        super().__init__(
            client, database_name, container_name, partition_key="/directive_id", default_ttl=-1
        )

    async def try_acquire(self, directive_id: str, slot: str, *, ttl: int = 3600) -> bool:
        from azure.cosmos.exceptions import CosmosResourceExistsError

        container = await self._get_container()
        doc = {
            "id": f"{directive_id}:{slot}",
            "directive_id": directive_id,
            "slot": slot,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl": int(ttl),
            "doc_type": "autonomous_lease",
            "schema_version": 1,
        }
        try:
            await container.create_item(doc)
            return True
        except CosmosResourceExistsError:
            return False


class _CosmosByIdRepository(_CosmosContainer):
    """Generic global by-id document store, partitioned by ``/id``.

    Backs the two global config stores that share this exact shape — autonomous
    directives and agent skills — a small set of operator-authored documents keyed
    by id (the per-user analogue is ``user_data.CosmosUserScopedRepository``).
    Volume is tiny, so the dominant "list all" read is a cheap cross-partition
    query and point reads/writes are partition-scoped by id. ``create`` is an
    atomic insert (raises ``CosmosResourceExistsError`` on a duplicate id, for a
    409); ``upsert`` is used for updates and idempotent seeding.
    """

    def __init__(self, client: Any, database_name: str, container_name: str) -> None:
        super().__init__(client, database_name, container_name, partition_key="/id")

    async def list_all(self) -> list[dict[str, Any]]:
        container = await self._get_container()
        items = container.query_items(query="SELECT * FROM c")
        docs: list[dict[str, Any]] = []
        async for item in items:
            docs.append(item)
        docs.sort(key=lambda d: (str(d.get("created_at") or ""), str(d.get("id") or "")))
        return docs

    async def get(self, item_id: str) -> dict[str, Any] | None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        try:
            return await container.read_item(item=item_id, partition_key=item_id)
        except CosmosResourceNotFoundError:
            return None

    async def create(self, doc: dict[str, Any]) -> dict[str, Any]:
        container = await self._get_container()
        await container.create_item(doc)
        return doc

    async def upsert(self, doc: dict[str, Any]) -> dict[str, Any]:
        container = await self._get_container()
        await container.upsert_item(doc)
        return doc

    async def delete(self, item_id: str) -> bool:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        try:
            await container.delete_item(item=item_id, partition_key=item_id)
            return True
        except CosmosResourceNotFoundError:
            return False


# ---------------------------------------------------------------------------
# Shared Cosmos client + provider/repository singletons
# ---------------------------------------------------------------------------

_cosmos_client: Any = None
_async_credential: Any = None
_history_provider: Any = None
_conversation_repo: Any = None
_autonomous_run_repo: Any = None
_autonomous_lease_repo: Any = None
_autonomous_directive_repo: Any = None
_skill_repo: Any = None

def _build_cosmos_client() -> Any:
    """Create a single shared async CosmosClient (key for local, MI for prod)."""
    from azure.cosmos.aio import CosmosClient

    endpoint = (os.getenv("AZURE_COSMOS_ENDPOINT") or "").strip()
    key = (os.getenv("AZURE_COSMOS_KEY") or "").strip() or None
    host = urlsplit(endpoint).hostname or ""
    kwargs: dict[str, Any] = {}
    if host in ("localhost", "127.0.0.1"):
        # Emulator: self-signed cert, rejects AAD tokens (use its well-known key),
        # and advertises its internal container IP — so pin the client to our
        # endpoint by disabling endpoint discovery.
        kwargs["connection_verify"] = False
        kwargs["enable_endpoint_discovery"] = False
        if not key:
            key = _EMULATOR_WELL_KNOWN_KEY

    global _async_credential
    if key:
        credential: Any = key
    else:
        from azure.identity.aio import DefaultAzureCredential

        # DefaultAzureCredential honours AZURE_AUTHORITY_HOST for Azure Government.
        _async_credential = DefaultAzureCredential()
        credential = _async_credential

    logger.info(
        "Cosmos client created (host=%s, auth=%s)",
        host,
        "key" if key else "managed-identity",
    )
    return CosmosClient(url=endpoint, credential=credential, **kwargs)


def get_cosmos_client() -> Any:
    """Return the lazily-created, shared async CosmosClient.

    Raises if Cosmos is unconfigured. Shared with the per-user repositories in
    ``user_data`` so the whole app uses a single client / connection pool.
    """
    global _cosmos_client
    _require_cosmos()
    if _cosmos_client is None:
        _cosmos_client = _build_cosmos_client()
    return _cosmos_client


def _require_cosmos() -> None:
    """Raise unless Cosmos is configured. There is no in-memory fallback by design."""
    if not (os.getenv("AZURE_COSMOS_ENDPOINT") or "").strip():
        raise RuntimeError(
            "Azure Cosmos DB is required but not configured (AZURE_COSMOS_ENDPOINT is unset). "
            "Run the Cosmos emulator locally (USE_COSMOS_EMULATOR=true and "
            "AZURE_COSMOS_ENDPOINT=https://localhost:8081/), or point AZURE_COSMOS_ENDPOINT at "
            "the deployed Cosmos account. Chat memory has no non-durable fallback."
        )


def get_history_provider() -> Any:
    """Return the cached Cosmos agent history provider.

    Requires Cosmos to be configured (emulator locally, real account when
    deployed); raises otherwise.
    """
    global _history_provider
    if _history_provider is None:
        from agent_framework.azure import CosmosHistoryProvider

        database = (os.getenv("AZURE_COSMOS_DATABASE_NAME") or "agent-memory").strip()
        container = (os.getenv("AZURE_COSMOS_CONTAINER_NAME") or "chat-history").strip()
        _history_provider = CosmosHistoryProvider(
            cosmos_client=get_cosmos_client(),
            database_name=database,
            container_name=container,
        )
        logger.info(
            "Durable Cosmos history provider enabled (db=%s, container=%s)",
            database,
            container,
        )
    return _history_provider


def get_conversation_repository() -> Any:
    """Return the cached Cosmos conversation-index repository.

    Requires Cosmos to be configured; raises otherwise.
    """
    global _conversation_repo
    if _conversation_repo is None:
        database = (os.getenv("AZURE_COSMOS_DATABASE_NAME") or "agent-memory").strip()
        container = (os.getenv("AZURE_COSMOS_CONVERSATIONS_CONTAINER") or "conversations").strip()
        _conversation_repo = CosmosConversationRepository(
            get_cosmos_client(),
            database,
            container,
        )
    return _conversation_repo


def get_autonomous_run_repository() -> Any:
    """Return the cached Cosmos autonomous-run audit repository.

    Requires Cosmos to be configured; raises otherwise.
    """
    global _autonomous_run_repo
    if _autonomous_run_repo is None:
        database = (os.getenv("AZURE_COSMOS_DATABASE_NAME") or "agent-memory").strip()
        container = (os.getenv("AZURE_COSMOS_AUTONOMOUS_CONTAINER") or "autonomous-runs").strip()
        _autonomous_run_repo = CosmosAutonomousRunRepository(
            get_cosmos_client(),
            database,
            container,
        )
    return _autonomous_run_repo


def get_autonomous_lease_repository() -> Any:
    """Return the cached Cosmos autonomous scheduler-lease repository.

    Requires Cosmos to be configured; raises otherwise.
    """
    global _autonomous_lease_repo
    if _autonomous_lease_repo is None:
        database = (os.getenv("AZURE_COSMOS_DATABASE_NAME") or "agent-memory").strip()
        container = (os.getenv("AZURE_COSMOS_LEASES_CONTAINER") or "autonomous-leases").strip()
        _autonomous_lease_repo = CosmosAutonomousLeaseRepository(
            get_cosmos_client(),
            database,
            container,
        )
    return _autonomous_lease_repo


def get_autonomous_directive_repository() -> Any:
    """Return the cached Cosmos autonomous-directive repository.

    Requires Cosmos to be configured; raises otherwise.
    """
    global _autonomous_directive_repo
    if _autonomous_directive_repo is None:
        database = (os.getenv("AZURE_COSMOS_DATABASE_NAME") or "agent-memory").strip()
        container = (os.getenv("AZURE_COSMOS_DIRECTIVES_CONTAINER") or "autonomous-directives").strip()
        _autonomous_directive_repo = _CosmosByIdRepository(
            get_cosmos_client(),
            database,
            container,
        )
    return _autonomous_directive_repo


def get_skill_repository() -> Any:
    """Return the cached Cosmos skill repository.

    Requires Cosmos to be configured; raises otherwise.
    """
    global _skill_repo
    if _skill_repo is None:
        database = (os.getenv("AZURE_COSMOS_DATABASE_NAME") or "agent-memory").strip()
        container = (os.getenv("AZURE_COSMOS_SKILLS_CONTAINER") or "skills").strip()
        _skill_repo = _CosmosByIdRepository(
            get_cosmos_client(),
            database,
            container,
        )
    return _skill_repo


def require_cosmos_configured() -> None:
    """Fail fast at startup unless Cosmos is configured (or a double was injected for tests)."""
    if _history_provider is not None or _conversation_repo is not None:
        return
    _require_cosmos()


async def close_cosmos() -> None:
    """Close the shared Cosmos client + credential (called on app shutdown)."""
    global _cosmos_client, _async_credential, _history_provider, _conversation_repo
    global _autonomous_run_repo, _autonomous_lease_repo, _autonomous_directive_repo, _skill_repo

    if _cosmos_client is not None:
        try:
            await _cosmos_client.close()
        except Exception:  # noqa: BLE001 — shutdown best-effort
            logger.debug("Error closing Cosmos client", exc_info=True)
    if _async_credential is not None:
        try:
            await _async_credential.close()
        except Exception:  # noqa: BLE001 — shutdown best-effort
            logger.debug("Error closing Cosmos credential", exc_info=True)
    _cosmos_client = None
    _async_credential = None
    _history_provider = None
    _conversation_repo = None
    _autonomous_run_repo = None
    _autonomous_lease_repo = None
    _autonomous_directive_repo = None
    _skill_repo = None
