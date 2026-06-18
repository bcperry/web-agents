"""Per-user Cosmos repositories for custom agents, agent customizations, and the
user memory profile.

Each datum is a small per-user collection partitioned by ``/user_id`` and stored
in its own container. The shared async ``CosmosClient`` is reused from
``cosmos_memory`` so the whole app uses one connection pool. Tests monkeypatch the
module-level singletons (``_custom_agents_repo`` etc.) with in-memory doubles.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import cosmos_memory

logger = logging.getLogger(__name__)


def _database_name() -> str:
    return (os.getenv("AZURE_COSMOS_DATABASE_NAME") or "agent-memory").strip()


def _container_name(env_var: str, default: str) -> str:
    return (os.getenv(env_var) or default).strip()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CosmosUserScopedRepository:
    """Generic per-user document collection, partitioned by ``/user_id``.

    Each document wraps an arbitrary JSON payload::

        {"id": item_id, "user_id": user_id, "data": <payload>,
         "created_at": iso, "updated_at": iso}

    The repository returns the bare ``data`` payloads (the wire shapes the
    frontend already uses); the wrapper fields are storage bookkeeping.
    """

    def __init__(self, container_name: str) -> None:
        self._container_name = container_name
        self._container: Any = None

    async def _get_container(self) -> Any:
        if self._container is None:
            from azure.cosmos import PartitionKey

            client = cosmos_memory.get_cosmos_client()
            database = await client.create_database_if_not_exists(_database_name())
            self._container = await database.create_container_if_not_exists(
                id=self._container_name,
                partition_key=PartitionKey(path="/user_id"),
            )
        return self._container

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        container = await self._get_container()
        items = container.query_items(
            query="SELECT * FROM c WHERE c.user_id = @uid ORDER BY c.created_at ASC",
            parameters=[{"name": "@uid", "value": user_id}],
            partition_key=user_id,
        )
        return [item["data"] async for item in items if isinstance(item.get("data"), dict)]

    async def get(self, user_id: str, item_id: str) -> dict[str, Any] | None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        try:
            doc = await container.read_item(item=item_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            return None
        data = doc.get("data")
        return data if isinstance(data, dict) else None

    async def upsert(self, user_id: str, item_id: str, data: dict[str, Any]) -> dict[str, Any]:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        now = _utcnow_iso()
        created_at = now
        try:
            existing = await container.read_item(item=item_id, partition_key=user_id)
            created_at = existing.get("created_at", now)
        except CosmosResourceNotFoundError:
            pass
        await container.upsert_item({
            "id": item_id,
            "user_id": user_id,
            "data": data,
            "created_at": created_at,
            "updated_at": now,
        })
        return data

    async def delete(self, user_id: str, item_id: str) -> bool:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        container = await self._get_container()
        try:
            await container.delete_item(item=item_id, partition_key=user_id)
            return True
        except CosmosResourceNotFoundError:
            return False


# ---------------------------------------------------------------------------
# Cached singletons (tests monkeypatch these with in-memory doubles)
# ---------------------------------------------------------------------------

_custom_agents_repo: Any = None
_agent_customizations_repo: Any = None
_user_profile_repo: Any = None


def get_custom_agents_repository() -> Any:
    global _custom_agents_repo
    if _custom_agents_repo is None:
        _custom_agents_repo = CosmosUserScopedRepository(
            _container_name("AZURE_COSMOS_CUSTOM_AGENTS_CONTAINER", "custom-agents")
        )
    return _custom_agents_repo


def get_agent_customizations_repository() -> Any:
    global _agent_customizations_repo
    if _agent_customizations_repo is None:
        _agent_customizations_repo = CosmosUserScopedRepository(
            _container_name("AZURE_COSMOS_AGENT_CUSTOMIZATIONS_CONTAINER", "agent-customizations")
        )
    return _agent_customizations_repo


def get_user_profile_repository() -> Any:
    global _user_profile_repo
    if _user_profile_repo is None:
        _user_profile_repo = CosmosUserScopedRepository(
            _container_name("AZURE_COSMOS_USER_PROFILES_CONTAINER", "user-profiles")
        )
    return _user_profile_repo
