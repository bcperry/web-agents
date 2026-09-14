"""Tests for the Cosmos memory layer: provider selection, conversation index, mapping."""

import asyncio
from uuid import uuid4

import pytest

import cosmos_memory
from tests._doubles import clear_cosmos_singletons


# ---------------------------------------------------------------------------
# T011 — provider / repository selection
# ---------------------------------------------------------------------------

def test_raises_when_cosmos_not_configured(monkeypatch):
    monkeypatch.delenv("AZURE_COSMOS_ENDPOINT", raising=False)
    clear_cosmos_singletons(monkeypatch)
    with pytest.raises(RuntimeError):
        cosmos_memory.get_history_provider()
    with pytest.raises(RuntimeError):
        cosmos_memory.get_conversation_repository()
    with pytest.raises(RuntimeError):
        cosmos_memory.require_cosmos_configured()


def test_cosmos_close_resets_user_repository_singletons():
    import user_data

    assert user_data._custom_agents_repo is not None
    asyncio.run(cosmos_memory.close_cosmos())
    assert user_data._custom_agents_repo is None
    assert user_data._agent_views_repo is None


def test_real_repository_passes_continuation_token_to_sdk():
    from types import SimpleNamespace

    calls = {}
    class Pages:
        continuation_token = "next-token"
        async def __anext__(self):
            async def records():
                yield {"id": "record", "user_id": "owner"}
            return records()
    class Items:
        def by_page(self, *, continuation_token):
            calls["cursor"] = continuation_token
            return Pages()
    def query_items(**kwargs):
        calls.update(kwargs)
        return Items()
    repo = cosmos_memory.CosmosConversationRepository(None, "test", "test")
    repo._container = SimpleNamespace(query_items=query_items)
    records, cursor = asyncio.run(repo.list_for_user("owner", limit=2, cursor="previous-token"))
    assert [record.id for record in records] == ["record"]
    assert calls["cursor"] == "previous-token"
    assert calls["partition_key"] == "owner"
    assert calls["max_item_count"] == 2
    assert cursor == "next-token"


def test_cosmos_selected_with_endpoint(monkeypatch):
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://localhost:8081/")
    # well-known public emulator key (valid base64; not a secret)
    monkeypatch.setenv(
        "AZURE_COSMOS_KEY",
        "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==",
    )
    monkeypatch.setenv("AZURE_COSMOS_DATABASE_NAME", "agent-memory")
    monkeypatch.setenv("AZURE_COSMOS_CONTAINER_NAME", "chat-history")
    clear_cosmos_singletons(monkeypatch)
    from agent_framework.azure import CosmosHistoryProvider

    assert isinstance(cosmos_memory.get_history_provider(), CosmosHistoryProvider)
    assert isinstance(
        cosmos_memory.get_conversation_repository(),
        cosmos_memory.CosmosConversationRepository,
    )


# ---------------------------------------------------------------------------
# Cosmos client credential selection (emulator key vs managed identity)
# ---------------------------------------------------------------------------


class _RecordingCosmosClient:
    """Stand-in for azure.cosmos.aio.CosmosClient that records constructor args."""

    def __init__(self, url, credential, **kwargs):
        self.url = url
        self.credential = credential
        self.kwargs = kwargs


@pytest.fixture
def recording_cosmos_client(monkeypatch):
    """Capture how _build_cosmos_client constructs the async CosmosClient."""
    import azure.cosmos.aio as cosmos_aio

    captured: dict[str, _RecordingCosmosClient] = {}

    def _factory(url, credential, **kwargs):
        client = _RecordingCosmosClient(url, credential, **kwargs)
        captured["client"] = client
        return client

    monkeypatch.setattr(cosmos_aio, "CosmosClient", _factory)
    return captured


def test_local_emulator_uses_well_known_key_when_no_key(monkeypatch, recording_cosmos_client):
    """Regression: against the emulator with no AZURE_COSMOS_KEY we must use the
    emulator's well-known master key. AAD/managed-identity tokens are rejected by
    the emulator with 401 'token does not have a valid signature'."""
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://localhost:8081/")
    monkeypatch.delenv("AZURE_COSMOS_KEY", raising=False)
    cosmos_memory._build_cosmos_client()
    client = recording_cosmos_client["client"]
    assert client.credential == cosmos_memory._EMULATOR_WELL_KNOWN_KEY
    assert client.kwargs.get("connection_verify") is False
    # The classic emulator advertises an unreachable container IP; discovery
    # must be disabled so the SDK stays on the provided localhost endpoint.
    assert client.kwargs.get("enable_endpoint_discovery") is False


def test_local_emulator_respects_explicit_key(monkeypatch, recording_cosmos_client):
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://127.0.0.1:8081/")
    monkeypatch.setenv("AZURE_COSMOS_KEY", "explicit-test-key")
    cosmos_memory._build_cosmos_client()
    client = recording_cosmos_client["client"]
    assert client.credential == "explicit-test-key"


@pytest.mark.parametrize("stale_key", ["", "stale-cloud-key"])
def test_remote_endpoint_uses_managed_identity_when_no_key(monkeypatch, recording_cosmos_client, stale_key):
    """A real (non-local) endpoint with no key must use DefaultAzureCredential and
    must NOT disable TLS verification or fall back to the emulator key."""
    import azure.identity.aio as identity_aio

    class _FakeCredential:
        pass

    monkeypatch.setattr(identity_aio, "DefaultAzureCredential", _FakeCredential)
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://acct.documents.azure.us/")
    monkeypatch.setenv("AZURE_COSMOS_KEY", stale_key)
    cosmos_memory._build_cosmos_client()
    client = recording_cosmos_client["client"]
    assert isinstance(client.credential, _FakeCredential)
    assert client.credential != cosmos_memory._EMULATOR_WELL_KNOWN_KEY
    assert "connection_verify" not in client.kwargs
    # Real (geo-replicated) accounts must keep endpoint discovery enabled.
    assert "enable_endpoint_discovery" not in client.kwargs


# ---------------------------------------------------------------------------
# Conversation repository CRUD + isolation — REAL Cosmos via the emulator
# ---------------------------------------------------------------------------

@pytest.mark.emulator
def test_repo_create_and_get_owned(cosmos_emulator):
    async def scenario():
        repo = cosmos_memory.get_conversation_repository()
        user = f"userA-{uuid4()}"
        try:
            record = await repo.create(user, "c1", "search", "Search Agent")
            assert record.id == "c1"
            assert record.user_id == user
            got = await repo.get_owned(user, "c1")
            assert got is not None
            assert got.profile_name == "Search Agent"
        finally:
            await repo.delete(user, "c1")
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


@pytest.mark.emulator
def test_repo_per_user_isolation(cosmos_emulator):
    async def scenario():
        repo = cosmos_memory.get_conversation_repository()
        user_a, user_b = f"userA-{uuid4()}", f"userB-{uuid4()}"
        try:
            await repo.create(user_a, "c1", "search", "Search Agent")
            assert await repo.get_owned(user_b, "c1") is None
            records, _ = await repo.list_for_user(user_b)
            assert records == []
        finally:
            await repo.delete(user_a, "c1")
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


@pytest.mark.emulator
@pytest.mark.parametrize("page_size", [50, 1])
def test_repo_list_orders_by_last_activity_desc(cosmos_emulator, page_size):
    async def scenario():
        repo = cosmos_memory.get_conversation_repository()
        user = f"u-{uuid4()}"
        try:
            await repo.create(user, "c1", "search", "A")
            await repo.create(user, "c2", "search", "B")
            await repo.touch(user, "c1", title="hello world")  # c1 becomes most recent
            records, cursor = await repo.list_for_user(user, limit=page_size)
            if len(records) > page_size:
                pytest.xfail("vNext emulator ignores max_item_count for ORDER BY queries; verify ordered pagination against Cosmos service")
            while cursor:
                page, cursor = await repo.list_for_user(user, limit=page_size, cursor=cursor)
                records.extend(page)
            assert [r.id for r in records] == ["c1", "c2"]
            assert records[0].title == "hello world"
        finally:
            await repo.delete(user, "c1")
            await repo.delete(user, "c2")
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


@pytest.mark.emulator
def test_repo_touch_sets_title_only_once(cosmos_emulator):
    async def scenario():
        repo = cosmos_memory.get_conversation_repository()
        user = f"u-{uuid4()}"
        try:
            await repo.create(user, "c1", "search", "A")
            await repo.touch(user, "c1", title="first message")
            await repo.touch(user, "c1", title="second message")
            got = await repo.get_owned(user, "c1")
            assert got.title == "first message"
        finally:
            await repo.delete(user, "c1")
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


@pytest.mark.emulator
@pytest.mark.parametrize("concurrent_action", ["delete", "update"])
def test_repo_touch_preserves_concurrent_changes(cosmos_emulator, monkeypatch, concurrent_action):
    async def scenario():
        repo = cosmos_memory.get_conversation_repository()
        user = f"u-{uuid4()}"
        try:
            await repo.create(user, "c1", "search", "A")
            container = await repo._get_container()
            read_item = container.read_item

            async def read_then_change(*args, **kwargs):
                item = await read_item(*args, **kwargs)
                if concurrent_action == "delete":
                    await container.delete_item(item="c1", partition_key=user)
                else:
                    await container.replace_item(item="c1", body={**item, "title": "first writer"})
                return item

            with monkeypatch.context() as patch:
                patch.setattr(container, "read_item", read_then_change)
                await repo.touch(user, "c1", title="late message")

            stored = await repo.get_owned(user, "c1")
            if concurrent_action == "delete":
                assert stored is None
            else:
                assert stored.title == "first writer"
        finally:
            await repo.delete(user, "c1")
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


@pytest.mark.emulator
def test_repo_delete_is_owner_scoped_and_idempotent(cosmos_emulator):
    async def scenario():
        repo = cosmos_memory.get_conversation_repository()
        user, other = f"u-{uuid4()}", f"other-{uuid4()}"
        try:
            await repo.create(user, "c1", "search", "A")
            assert await repo.delete(other, "c1") is False  # not owner
            assert await repo.get_owned(user, "c1") is not None
            assert await repo.delete(user, "c1") is True
            assert await repo.get_owned(user, "c1") is None
            assert await repo.delete(user, "c1") is False  # already gone
        finally:
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())


def test_conversation_record_wire_shape():
    record = cosmos_memory.ConversationRecord(
        id="c1", user_id="u", profile_id="search", profile_name="Search Agent",
        title="Hello", created_at="t0", last_activity_at="t1",
    )
    wire = record.to_wire()
    assert wire == {
        "id": "c1",
        "profileId": "search",
        "profileName": "Search Agent",
        "description": "Hello",
        "createdAt": "t0",
        "lastActivityAt": "t1",
        "customAgentId": None,
        "usedBuiltInOverride": False,
        "baseProfileId": None,
        "overrideUpdatedAt": None,
    }
    # round-trips through the Cosmos document form
    assert cosmos_memory.ConversationRecord.from_doc(record.to_doc()).id == "c1"


# ---------------------------------------------------------------------------
# Stored Message -> ChatMessage wire mapping
# ---------------------------------------------------------------------------

def test_messages_to_wire_maps_user_and_assistant():
    from agent_framework._types import Content, Message
    from streaming import messages_to_wire

    msgs = [
        Message(role="user", contents=[Content.from_text("hi there")]),
        Message(role="assistant", contents=[Content.from_text("hello back")]),
    ]
    wire = messages_to_wire(msgs)
    assert [m["role"] for m in wire] == ["user", "assistant"]
    assert wire[0]["content"] == "hi there"
    assert wire[1]["content"] == "hello back"


def test_messages_to_wire_strips_user_time_marker():
    from agent_framework._types import Content, Message
    from streaming import messages_to_wire, with_user_time

    msgs = [
        Message(role="user", contents=[Content.from_text(with_user_time("hi there", "Wed Jun 18 2026 14:30:00 GMT-0700"))]),
        Message(role="assistant", contents=[Content.from_text("hello back")]),
    ]
    wire = messages_to_wire(msgs)
    # The timestamp marker is invisible in the wire form the UI renders.
    assert wire[0]["content"] == "hi there"
    assert wire[1]["content"] == "hello back"


# ---------------------------------------------------------------------------
# T012 — emulator integration (skips when the emulator is not running)
# ---------------------------------------------------------------------------

@pytest.mark.emulator
def test_emulator_memory_round_trip(cosmos_emulator):
    """Persist a turn via the real provider, simulate a restart, reload by id.

    The whole scenario runs inside a single event loop: the async Cosmos client
    (an aiohttp session) is bound to the loop it is created on, so spreading the
    steps across multiple ``asyncio.run`` calls would raise "Event loop is
    closed". The production app uses one long-lived loop, matching this shape.
    """
    import uuid as _uuid
    from agent_framework._types import Content, Message
    from agent_framework.azure import CosmosHistoryProvider
    from azure.core.exceptions import AzureError

    user = "emu-user"
    conv = str(_uuid.uuid4())

    async def _scenario():
        try:
            repo = cosmos_memory.get_conversation_repository()
            provider = cosmos_memory.get_history_provider()
            assert isinstance(provider, CosmosHistoryProvider)

            await repo.create(user, conv, "search", "Search Agent")
            await provider.save_messages(
                conv, [Message(role="user", contents=[Content.from_text("remember falcon")])]
            )

            # Simulated restart: drop + rebuild singletons (same loop), reload by id
            await cosmos_memory.close_cosmos()
            provider2 = cosmos_memory.get_history_provider()
            loaded = await provider2.get_messages(conv)
            assert any("falcon" in (getattr(m, "text", "") or "") for m in loaded)

            # ownership + cleanup
            repo2 = cosmos_memory.get_conversation_repository()
            assert await repo2.get_owned("other", conv) is None
            await provider2.clear(conv)
            await repo2.delete(user, conv)
        finally:
            await cosmos_memory.close_cosmos()

    try:
        asyncio.run(_scenario())
    except (AzureError, OSError) as exc:
        pytest.skip(
            f"Cosmos emulator data plane not reachable ({type(exc).__name__}). "
            "The classic emulator advertises its container IP; set "
            "AZURE_COSMOS_EMULATOR_IP_ADDRESS_OVERRIDE or use the vnext-preview image."
        )
