"""Tests for session orchestration helpers."""

from session_orchestration import sanitize_mcp_result_error


def test_sanitize_mcp_result_error_removes_credentials_and_tokens():
    error = (
        "GET https://example.test/mcp?api_key=secret&code=abc failed "
        "Authorization: Bearer eyJsecret token password=hidden connectionString=Server=tcp"
    )

    sanitized = sanitize_mcp_result_error(error)

    assert "secret" not in sanitized
    assert "Bearer" not in sanitized
    assert "api_key=" not in sanitized
    assert "code=" not in sanitized
    assert "password=" not in sanitized
    assert "connectionString=" not in sanitized
    assert "https://example.test/mcp" in sanitized