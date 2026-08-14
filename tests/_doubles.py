"""In-memory test doubles for the Cosmos memory layer.

These live in the test suite, not production code. The FastAPI app requires a
real Cosmos backend (the emulator locally); the real ``CosmosConversationRepository``
is covered by the emulator-backed tests in ``test_cosmos_memory.py``. This
loop-independent in-memory index lets the broader API tests seed data with
``asyncio.run`` and then read it back through ``TestClient`` (a different event
loop) without a live emulator and without the async-client loop-binding problem.
"""

from __future__ import annotations

from datetime import datetime, timezone

from cosmos_memory import AutonomousRunRecord, ConversationRecord


class InMemoryConversationRepository:
    """Loop-independent in-memory conversation index (test double)."""

    def __init__(self) -> None:
        self._by_user: dict[str, dict[str, ConversationRecord]] = {}

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
        self._by_user.setdefault(user_id, {})[conversation_id] = record
        return record

    async def list_for_user(
        self, user_id: str, *, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[ConversationRecord], str | None]:
        records = sorted(
            self._by_user.get(user_id, {}).values(),
            key=lambda r: r.last_activity_at,
            reverse=True,
        )
        return records[: max(0, limit)], None

    async def get_owned(self, user_id: str, conversation_id: str) -> ConversationRecord | None:
        return self._by_user.get(user_id, {}).get(conversation_id)

    async def touch(self, user_id: str, conversation_id: str, *, title: str | None = None) -> None:
        record = self._by_user.get(user_id, {}).get(conversation_id)
        if record is None:
            return
        record.last_activity_at = datetime.now(timezone.utc).isoformat()
        if title and not record.title:
            record.title = title

    async def delete(self, user_id: str, conversation_id: str) -> bool:
        user_convs = self._by_user.get(user_id, {})
        if conversation_id in user_convs:
            del user_convs[conversation_id]
            return True
        return False


class InMemoryAutonomousRunRepository:
    """Loop-independent in-memory autonomous-run audit log (test double).

    Mirrors ``CosmosAutonomousRunRepository``: create/list/get, recency-ordered
    (most-recent-first), with a stable insertion-sequence tiebreaker so runs that
    share a timestamp still order deterministically.
    """

    def __init__(self) -> None:
        self._runs: list[tuple[int, AutonomousRunRecord]] = []
        self._seq = 0

    async def create_run(self, record: AutonomousRunRecord) -> AutonomousRunRecord:
        self._runs.append((self._seq, record))
        self._seq += 1
        return record

    async def list_runs(
        self, *, limit: int = 50, directive_id: str | None = None
    ) -> list[AutonomousRunRecord]:
        rows = self._runs
        if directive_id:
            rows = [row for row in rows if row[1].directive_id == directive_id]
        ordered = sorted(rows, key=lambda row: (row[1].started_at, row[0]), reverse=True)
        return [record for _, record in ordered[: max(0, min(limit, 200))]]

    async def get_run(self, run_id: str, directive_id: str) -> AutonomousRunRecord | None:
        for _, record in self._runs:
            if record.id == run_id and record.directive_id == directive_id:
                return record
        return None


class InMemoryAutonomousLeaseRepository:
    """Loop-independent in-memory scheduler lease (test double).

    The first ``try_acquire`` of a ``{directive_id}:{slot}`` pair returns True; any
    later claim of the same pair returns False — the in-memory analogue of the
    atomic Cosmos create that guarantees at-most-once execution per slot.
    """

    def __init__(self) -> None:
        self._claimed: set[str] = set()

    async def try_acquire(self, directive_id: str, slot: str, *, ttl: int = 3600) -> bool:
        key = f"{directive_id}:{slot}"
        if key in self._claimed:
            return False
        self._claimed.add(key)
        return True


class InMemoryByIdRepository:
    """Loop-independent in-memory global by-id document store (test double).

    Mirrors ``cosmos_memory._CosmosByIdRepository`` — the shared backing for the
    autonomous directive store and the skill store: list/get/create/upsert/delete
    keyed by id. ``create`` raises ``CosmosResourceExistsError`` on a duplicate id
    (as the real atomic create does). Accepts an optional ``initial`` list of docs
    so the autouse fixture can seed it from the defaults (as Cosmos is seeded at
    startup in production).
    """

    def __init__(self, initial: list[dict] | None = None) -> None:
        self._by_id: dict[str, dict] = {}
        for doc in initial or []:
            self._by_id[str(doc["id"])] = dict(doc)

    async def list_all(self) -> list[dict]:
        return sorted(
            (dict(d) for d in self._by_id.values()),
            key=lambda d: (str(d.get("created_at") or ""), str(d.get("id") or "")),
        )

    async def get(self, item_id: str) -> dict | None:
        doc = self._by_id.get(item_id)
        return dict(doc) if doc is not None else None

    async def create(self, doc: dict) -> dict:
        from azure.cosmos.exceptions import CosmosResourceExistsError

        item_id = str(doc["id"])
        if item_id in self._by_id:
            raise CosmosResourceExistsError(message=f"Item already exists: {item_id}")
        self._by_id[item_id] = dict(doc)
        return doc

    async def upsert(self, doc: dict) -> dict:
        self._by_id[str(doc["id"])] = dict(doc)
        return doc

    async def delete(self, item_id: str) -> bool:
        return self._by_id.pop(item_id, None) is not None


class InMemoryUserScopedRepository:
    """Loop-independent in-memory per-user collection (test double for user_data)."""

    def __init__(self) -> None:
        self._by_user: dict[str, dict[str, dict]] = {}

    async def list_for_user(self, user_id: str) -> list[dict]:
        return list(self._by_user.get(user_id, {}).values())

    async def get(self, user_id: str, item_id: str) -> dict | None:
        return self._by_user.get(user_id, {}).get(item_id)

    async def create(self, user_id: str, item_id: str, data: dict) -> dict:
        from azure.cosmos.exceptions import CosmosResourceExistsError

        items = self._by_user.setdefault(user_id, {})
        if item_id in items:
            raise CosmosResourceExistsError(message=f"Item already exists: {item_id}")
        items[item_id] = data
        return data

    async def upsert(self, user_id: str, item_id: str, data: dict) -> dict:
        self._by_user.setdefault(user_id, {})[item_id] = data
        return data

    async def delete(self, user_id: str, item_id: str) -> bool:
        items = self._by_user.get(user_id, {})
        if item_id in items:
            del items[item_id]
            return True
        return False


class InMemoryAgentViewRepository:
    """Loop-independent in-memory agent view store (test double for user_data).

    Mirrors ``CosmosAgentViewRepository``: flat documents partitioned by user, with
    the conversation listing returned oldest-first (a stable insertion-sequence
    tiebreaker keeps ordering deterministic when timestamps collide).
    """

    def __init__(self) -> None:
        self._by_user: dict[str, dict[str, tuple[int, dict]]] = {}
        self._seq = 0

    async def list_for_conversation(self, user_id: str, conversation_id: str) -> list[dict]:
        rows = [
            row for row in self._by_user.get(user_id, {}).values()
            if row[1].get("conversation_id") == conversation_id
        ]
        ordered = sorted(rows, key=lambda row: (str(row[1].get("created_at") or ""), row[0]))
        return [dict(doc) for _, doc in ordered]

    async def get(self, user_id: str, view_id: str) -> dict | None:
        row = self._by_user.get(user_id, {}).get(view_id)
        return dict(row[1]) if row is not None else None

    async def create(self, document: dict) -> dict:
        user_id = str(document["user_id"])
        self._by_user.setdefault(user_id, {})[str(document["id"])] = (self._seq, dict(document))
        self._seq += 1
        return document

    async def delete(self, user_id: str, view_id: str) -> bool:
        return self._by_user.get(user_id, {}).pop(view_id, None) is not None


def clear_cosmos_singletons(monkeypatch) -> None:
    """Clear cosmos_memory + user_data cached singletons for a test, via monkeypatch.

    Production has no reset/injection seams; tests reach the module-level
    singletons through monkeypatch, which auto-reverts them at teardown.
    """
    import cosmos_memory
    import user_data

    for name in ("_cosmos_client", "_async_credential", "_history_provider", "_conversation_repo",
                 "_autonomous_run_repo", "_autonomous_lease_repo", "_autonomous_directive_repo",
                 "_skill_repo"):
        monkeypatch.setattr(cosmos_memory, name, None)
    for name in ("_custom_agents_repo", "_agent_customizations_repo", "_user_profile_repo",
                 "_user_skills_repo", "_agent_views_repo"):
        monkeypatch.setattr(user_data, name, None)
