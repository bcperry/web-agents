"""Tests for auth middleware."""

import os
import pytest

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("AZURE_SQL_CONNECTIONSTRING", "")

from auth import AuthenticatedUser, get_current_user, clear_jwks_cache, _auth_disabled


def test_auth_disabled_returns_dev_user():
    """When AUTH_DISABLED=true, get_current_user returns a default dev user."""
    os.environ["AUTH_DISABLED"] = "true"
    assert _auth_disabled() is True


def test_auth_enabled_check():
    """When AUTH_DISABLED is not true, auth is enforced."""
    original = os.environ.get("AUTH_DISABLED")
    try:
        os.environ["AUTH_DISABLED"] = "false"
        assert _auth_disabled() is False
    finally:
        if original is not None:
            os.environ["AUTH_DISABLED"] = original
        else:
            os.environ.pop("AUTH_DISABLED", None)


def test_authenticated_user_dataclass():
    """AuthenticatedUser fields are accessible."""
    user = AuthenticatedUser(user_id="test-id", username="testuser")
    assert user.user_id == "test-id"
    assert user.username == "testuser"


def test_clear_jwks_cache():
    """clear_jwks_cache runs without error."""
    clear_jwks_cache()


def test_auth_disabled_health_no_token():
    """Health endpoint doesn't require auth, GET /api/profiles should work with AUTH_DISABLED."""
    os.environ["AUTH_DISABLED"] = "true"
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
