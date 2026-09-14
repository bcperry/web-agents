"""Tests for auth middleware."""

import asyncio
import os
from unittest.mock import AsyncMock

import pytest
from fastapi.security import HTTPAuthorizationCredentials

os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("AZURE_SQL_CONNECTIONSTRING", "")

import auth
from auth import (
    AuthenticatedUser,
    _auth_disabled,
    _authenticated_user_from_payload,
    clear_jwks_cache,
    get_current_user,
)


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


def test_authenticated_user_carries_validated_tenant_and_group_claims():
    user = _authenticated_user_from_payload(
        {
            "oid": "user-1",
            "preferred_username": "user@example.test",
            "tid": "tenant-1",
            "groups": ["group-1", "group-2"],
        }
    )

    assert user.tenant_id == "tenant-1"
    assert user.group_ids == ("group-1", "group-2")


def test_authenticated_user_ignores_a_non_list_groups_claim():
    user = _authenticated_user_from_payload(
        {"oid": "user-1", "tid": "tenant-1", "_claim_names": {"groups": "src1"}}
    )

    assert user.group_ids == ()


def test_clear_jwks_cache():
    """clear_jwks_cache runs without error."""
    clear_jwks_cache()


def test_missing_signing_key_refreshes_jwks(monkeypatch):
    """A key rotation refreshes stale JWKS before rejecting the token."""
    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("AZURE_AD_TENANT_ID", "tenant-id")
    monkeypatch.setenv("AZURE_AD_CLIENT_ID", "client-id")
    fetch_jwks = AsyncMock(
        side_effect=[
            {"keys": [{"kid": "old-key"}]},
            {"keys": [{"kid": "new-key"}]},
        ]
    )
    monkeypatch.setattr(auth, "_fetch_jwks", fetch_jwks)
    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda token: {"kid": "new-key"})
    monkeypatch.setattr(
        auth.jwt,
        "decode",
        lambda *args, **kwargs: {"oid": "user-id", "preferred_username": "user@example.com"},
    )

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    user = asyncio.run(get_current_user(None, credentials))

    assert user.user_id == "user-id"
    assert fetch_jwks.await_count == 2
    assert fetch_jwks.await_args_list[1].kwargs == {"force_refresh": True}


def test_auth_disabled_health_no_token():
    """Health endpoint doesn't require auth, GET /api/profiles should work with AUTH_DISABLED."""
    os.environ["AUTH_DISABLED"] = "true"
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
