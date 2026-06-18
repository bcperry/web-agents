"""Tests for the Cosmos-direct user-profile memory tools.

The ``_cosmos_doubles`` autouse fixture (conftest.py) backs ``get_user_profile_repository``
with a loop-independent in-memory repository, so these exercise the real tool logic
without a live emulator.
"""

import asyncio

from tools import build_user_profile_tools


class TestGetUserProfile:
    def test_returns_no_profile_message_when_empty(self):
        tools = build_user_profile_tools("user1")
        result = asyncio.run(tools["get_user_profile"]())
        assert "No user profile found" in result

    def test_returns_json_after_save(self):
        tools = build_user_profile_tools("user1")

        async def scenario():
            await tools["save_user_profile"]("Alex", "dark mode", "likes Python")
            return await tools["get_user_profile"]()

        result = asyncio.run(scenario())
        assert '"name": "Alex"' in result
        assert '"preferences": "dark mode"' in result
        assert '"notes": "likes Python"' in result


class TestSaveUserProfile:
    def test_saves_valid_profile(self):
        tools = build_user_profile_tools("user1")

        async def scenario():
            saved = await tools["save_user_profile"]("Alex", "dark mode, concise answers", "enjoys hiking")
            got = await tools["get_user_profile"]()
            return saved, got

        saved, got = asyncio.run(scenario())
        assert "saved successfully" in saved
        assert '"name": "Alex"' in saved
        assert '"preferences": "dark mode, concise answers"' in got

    def test_rejects_empty_name(self):
        tools = build_user_profile_tools("user1")
        result = asyncio.run(tools["save_user_profile"](""))
        assert "Error" in result
        assert "name" in result

    def test_rejects_whitespace_name(self):
        tools = build_user_profile_tools("user1")
        result = asyncio.run(tools["save_user_profile"]("   "))
        assert "Error" in result
        assert "name" in result

    def test_defaults_preferences_and_notes_to_empty(self):
        tools = build_user_profile_tools("user1")

        async def scenario():
            await tools["save_user_profile"]("Alex")
            return await tools["get_user_profile"]()

        got = asyncio.run(scenario())
        assert '"preferences": ""' in got
        assert '"notes": ""' in got

    def test_strips_whitespace(self):
        tools = build_user_profile_tools("user1")
        result = asyncio.run(tools["save_user_profile"]("  Alex  ", "  dark mode  ", "  notes here  "))
        assert '"name": "Alex"' in result
        assert '"preferences": "dark mode"' in result
        assert '"notes": "notes here"' in result

    def test_overwrites_existing_profile(self):
        tools = build_user_profile_tools("user1")

        async def scenario():
            await tools["save_user_profile"]("Old", "old pref", "old notes")
            await tools["save_user_profile"]("New", "new pref", "new notes")
            return await tools["get_user_profile"]()

        got = asyncio.run(scenario())
        assert '"name": "New"' in got
        assert '"preferences": "new pref"' in got
        assert '"notes": "new notes"' in got

    def test_records_updated_at(self):
        tools = build_user_profile_tools("user1")

        async def scenario():
            await tools["save_user_profile"]("Alex")
            return await tools["get_user_profile"]()

        got = asyncio.run(scenario())
        assert '"updatedAt"' in got

    def test_profiles_are_isolated_per_user(self):
        async def scenario():
            await build_user_profile_tools("user1")["save_user_profile"]("Alex")
            return await build_user_profile_tools("user2")["get_user_profile"]()

        got = asyncio.run(scenario())
        assert "No user profile found" in got
