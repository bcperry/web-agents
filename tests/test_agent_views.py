"""Tests for the agent view record: validation, persistence, and the FIFO cap.

The API surface (ownership, the permission broker, rate limits) is covered in
``test_agent_views_api.py``.
"""

import asyncio

import pytest

import agent_views
import user_data
from tests._doubles import InMemoryAgentViewRepository


@pytest.fixture
def views_repo(monkeypatch):
    repo = InMemoryAgentViewRepository()
    monkeypatch.setattr(user_data, "_agent_views_repo", repo)
    return repo


def test_validate_view_rejects_empty_title():
    rejection = agent_views.validate_view("   ", "<p>hi</p>")

    assert rejection is not None
    assert rejection["reason"] == "empty_title"


def test_validate_view_rejects_empty_html():
    rejection = agent_views.validate_view("Title", "   ")

    assert rejection is not None
    assert rejection["reason"] == "empty_html"


def test_validate_view_rejects_oversize_html(monkeypatch):
    monkeypatch.setattr(agent_views, "MAX_AGENT_VIEW_CHARS", 10)

    rejection = agent_views.validate_view("Title", "<p>" + "x" * 50 + "</p>")

    assert rejection is not None
    assert rejection["reason"] == "too_large"
    assert rejection["limit"] == 10
    assert rejection["chars"] > 10


def test_validate_view_rejects_overlong_title():
    rejection = agent_views.validate_view("t" * 200, "<p>hi</p>")

    assert rejection is not None
    assert rejection["reason"] == "title_too_long"


def test_validate_view_accepts_a_reasonable_view():
    assert agent_views.validate_view("Readiness", "<p>hi</p>") is None


def test_save_view_persists_and_returns_a_record(views_repo):
    async def scenario():
        record = await agent_views.save_view(
            user_id="userA",
            conversation_id="conv-1",
            title="  Readiness  ",
            html="<p>hi</p>",
            profile_id="hybrid",
        )

        assert record.title == "Readiness"
        assert record.chars == len("<p>hi</p>")
        assert record.source == "chat"
        stored = await views_repo.get("userA", record.id)
        assert stored["conversation_id"] == "conv-1"
        assert stored["html"] == "<p>hi</p>"

    asyncio.run(scenario())


def test_save_view_evicts_the_oldest_past_the_cap(views_repo, monkeypatch):
    monkeypatch.setattr(agent_views, "MAX_AGENT_VIEWS_PER_CONVERSATION", 3)

    async def scenario():
        created = [
            await agent_views.save_view(
                user_id="userA", conversation_id="conv-1", title=f"V{i}", html=f"<p>{i}</p>"
            )
            for i in range(5)
        ]

        remaining = await agent_views.list_views("userA", "conv-1")

        assert [r.title for r in remaining] == ["V2", "V3", "V4"]
        assert await views_repo.get("userA", created[0].id) is None

    asyncio.run(scenario())


def test_list_views_is_scoped_to_one_conversation(views_repo):
    async def scenario():
        await agent_views.save_view(
            user_id="userA", conversation_id="conv-1", title="A", html="<p>a</p>"
        )
        await agent_views.save_view(
            user_id="userA", conversation_id="conv-2", title="B", html="<p>b</p>"
        )

        assert [r.title for r in await agent_views.list_views("userA", "conv-1")] == ["A"]
        assert [r.title for r in await agent_views.list_views("userA", "conv-2")] == ["B"]

    asyncio.run(scenario())


def test_views_are_isolated_between_users(views_repo):
    async def scenario():
        mine = await agent_views.save_view(
            user_id="userA", conversation_id="conv-1", title="Mine", html="<p>a</p>"
        )

        assert await agent_views.get_view("userB", "conv-1", mine.id) is None
        assert await agent_views.list_views("userB", "conv-1") == []

    asyncio.run(scenario())


def test_get_view_requires_a_matching_conversation(views_repo):
    async def scenario():
        record = await agent_views.save_view(
            user_id="userA", conversation_id="conv-1", title="A", html="<p>a</p>"
        )

        assert await agent_views.get_view("userA", "conv-1", record.id) is not None
        assert await agent_views.get_view("userA", "conv-2", record.id) is None

    asyncio.run(scenario())


def test_delete_views_for_conversation_removes_only_that_conversation(views_repo):
    async def scenario():
        await agent_views.save_view(
            user_id="userA", conversation_id="conv-1", title="A", html="<p>a</p>"
        )
        await agent_views.save_view(
            user_id="userA", conversation_id="conv-1", title="B", html="<p>b</p>"
        )
        keeper = await agent_views.save_view(
            user_id="userA", conversation_id="conv-2", title="C", html="<p>c</p>"
        )

        deleted = await agent_views.delete_views_for_conversation("userA", "conv-1")

        assert deleted == 2
        assert await agent_views.list_views("userA", "conv-1") == []
        assert (await agent_views.get_view("userA", "conv-2", keeper.id)) is not None

    asyncio.run(scenario())


def test_record_wire_shapes_split_summary_and_content():
    record = agent_views.AgentViewRecord(
        id="v1",
        user_id="userA",
        conversation_id="conv-1",
        title="Readiness",
        html="<p>hi</p>",
        profile_id="hybrid",
        created_at="2026-08-14T00:00:00+00:00",
        chars=9,
        source="chat",
    )

    assert "html" not in record.to_summary()
    assert record.to_summary()["viewId"] == "v1"
    assert record.to_wire()["html"] == "<p>hi</p>"


def test_unattended_runs_are_marked_by_their_session_convention(views_repo):
    async def scenario():
        attended = await agent_views.save_view(
            user_id="sys", conversation_id="conv-1", title="A", html="<p>a</p>"
        )
        unattended = await agent_views.save_view(
            user_id="sys", conversation_id="autonomous-duty-officer", title="B", html="<p>b</p>"
        )

        assert attended.source == "chat"
        assert unattended.source == "autonomous"

    asyncio.run(scenario())
