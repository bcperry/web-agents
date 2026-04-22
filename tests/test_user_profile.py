"""Tests for UserProfileStore tool methods."""

from tools import UserProfileStore


class TestGetUserProfile:
    def test_returns_no_profile_message_when_empty(self):
        store = UserProfileStore()
        result = store.get_user_profile()
        assert "No user profile found" in result

    def test_returns_json_when_profile_exists(self):
        store = UserProfileStore({"name": "Alex", "preferences": "dark mode", "notes": "likes Python"})
        result = store.get_user_profile()
        assert '"name": "Alex"' in result
        assert '"preferences": "dark mode"' in result
        assert '"notes": "likes Python"' in result


class TestSaveUserProfile:
    def test_saves_valid_profile(self):
        store = UserProfileStore()
        result = store.save_user_profile("Alex", "dark mode, concise answers", "enjoys hiking")
        assert "saved successfully" in result
        assert '"name": "Alex"' in result
        get_result = store.get_user_profile()
        assert '"preferences": "dark mode, concise answers"' in get_result

    def test_rejects_empty_name(self):
        store = UserProfileStore()
        result = store.save_user_profile("")
        assert "Error" in result
        assert "name" in result

    def test_rejects_whitespace_name(self):
        store = UserProfileStore()
        result = store.save_user_profile("   ")
        assert "Error" in result
        assert "name" in result

    def test_defaults_preferences_and_notes_to_empty(self):
        store = UserProfileStore()
        result = store.save_user_profile("Alex")
        assert "saved successfully" in result
        get_result = store.get_user_profile()
        assert '"preferences": ""' in get_result
        assert '"notes": ""' in get_result

    def test_strips_whitespace(self):
        store = UserProfileStore()
        result = store.save_user_profile("  Alex  ", "  dark mode  ", "  notes here  ")
        assert "saved successfully" in result
        assert '"name": "Alex"' in result
        assert '"preferences": "dark mode"' in result
        assert '"notes": "notes here"' in result

    def test_overwrites_existing_profile(self):
        store = UserProfileStore({"name": "Old", "preferences": "old pref", "notes": "old notes"})
        store.save_user_profile("New", "new pref", "new notes")
        get_result = store.get_user_profile()
        assert '"name": "New"' in get_result
        assert '"preferences": "new pref"' in get_result
        assert '"notes": "new notes"' in get_result
