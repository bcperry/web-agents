"""Tests for request retry classification and session behavior."""

from unittest.mock import MagicMock
from session_data import SessionData, _sessions
from app_context import DEFAULT_MAX_USER_INPUT_CHARS
from streaming import is_retryable_error
from agent_framework._types import UsageDetails


def _usage_value(usage: UsageDetails, key: str):
    if isinstance(usage, dict):
        return usage.get(key)
    return getattr(usage, key)


def _make_session(session_id: str = "test-session"):
    return SessionData(
        session_id=session_id,
        user_id="dev-user",
        profile_id="test-profile",
        profile_name="Test Profile",
        agent=MagicMock(),
        agent_session=MagicMock(),
        tools=[],
        eval_trace_logger=MagicMock(),
        prompt_logical_profile="test-profile",
    )


class TestIsRetryableError:
    """Test the is_retryable_error helper function."""

    def test_detects_429_in_message(self) -> None:
        """Should detect 429 status code in error message."""
        error = Exception("Error: 429 Too Many Requests")
        assert is_retryable_error(error) is True

    def test_detects_too_many_requests_message(self) -> None:
        """Should detect 'Too Many Requests' in error message."""
        error = Exception("Server returned Too Many Requests")
        assert is_retryable_error(error) is True

    def test_detects_rate_limit_in_message(self) -> None:
        """Should detect 'rate_limit' in error message (case insensitive)."""
        error = Exception("Request failed due to rate_limit exceeded")
        assert is_retryable_error(error) is True

    def test_detects_rate_limit_uppercase(self) -> None:
        """Should detect 'RATE_LIMIT' in error message (case insensitive)."""
        error = Exception("RATE_LIMIT error occurred")
        assert is_retryable_error(error) is True

    def test_detects_capacity_in_message(self) -> None:
        """Should detect 'capacity' in error message (case insensitive)."""
        error = Exception("Service at capacity, please retry later")
        assert is_retryable_error(error) is True

    def test_detects_capacity_uppercase(self) -> None:
        """Should detect 'CAPACITY' in error message (case insensitive)."""
        error = Exception("CAPACITY exceeded")
        assert is_retryable_error(error) is True

    def test_does_not_match_other_errors(self) -> None:
        """Should not match unrelated errors."""
        error = Exception("Connection timeout")
        assert is_retryable_error(error) is False

    def test_does_not_match_500_error(self) -> None:
        """Should not match 500 internal server error."""
        error = Exception("Error: 500 Internal Server Error")
        assert is_retryable_error(error) is False

    def test_does_not_match_empty_message(self) -> None:
        """Should not match empty error message."""
        error = Exception("")
        assert is_retryable_error(error) is False


class TestRetryLogicBehavior:
    """Tests for retry classification behavior."""

    def test_retryable_error_is_classified(self) -> None:
        """429 errors should be classified as retryable."""
        rate_limit_error = Exception("429 Too Many Requests")
        assert is_retryable_error(rate_limit_error) is True

    def test_non_retryable_error_is_not_classified(self) -> None:
        """Non-429 errors should not be classified as retryable."""
        regular_error = Exception("Connection timeout")
        assert is_retryable_error(regular_error) is False

    def test_rate_limit_error_type_detection(self) -> None:
        """Should detect RateLimitError type in exception."""
        # Simulate what a RateLimitError type check would return
        class RateLimitError(Exception):
            pass
        
        error = RateLimitError("Rate limit exceeded")
        assert is_retryable_error(error) is True

    def test_azure_openai_capacity_error(self) -> None:
        """Should detect Azure OpenAI capacity errors."""
        error = Exception("The server is currently at capacity. Please try again later.")
        assert is_retryable_error(error) is True

    def test_openai_rate_limit_header_error(self) -> None:
        """Should detect OpenAI rate limit errors with header info."""
        error = Exception("Rate limit reached for requests. Please retry after 60 seconds.")
        assert is_retryable_error(error) is True


class TestSessionManagement:
    """Test FastAPI session management endpoints."""

    def test_stream_error_does_not_expose_exception_details(self, client, monkeypatch):
        from api_routes import sessions

        async def failing_stream(*args, **kwargs):
            raise RuntimeError("https://internal.example/api?key=private-test-key")
            yield

        monkeypatch.setattr(sessions, "stream_agent_response", failing_stream)
        monkeypatch.setitem(_sessions, "error-test", _make_session("error-test"))

        response = client.post("/api/sessions/error-test/messages", json={"content": "hello"})

        assert response.status_code == 200
        assert "event: error" in response.text
        assert "event: done" in response.text
        assert "private-test-key" not in response.text
        assert "internal.example" not in response.text

    def test_delete_session_cleans_up(self, client) -> None:
        """delete_session should remove session from store."""

        _sessions.clear()
        _sessions["cleanup-test"] = _make_session("cleanup-test")

        response = client.delete("/api/sessions/cleanup-test")

        assert response.status_code == 204
        assert "cleanup-test" not in _sessions

class TestTokenUsage:
    """Test token usage tracking functionality."""

    def test_session_data_initializes_usage(self) -> None:
        """SessionData should initialize usage tracking."""
        assert _usage_value(_make_session().usage, "total_token_count") is None


    def test_delete_session_logs_usage(self, client, caplog) -> None:
        """delete_session should log token usage on cleanup."""

        _sessions.clear()
        _sessions["usage-test"] = _make_session("usage-test")

        with caplog.at_level("INFO", logger="main"):
            response = client.delete("/api/sessions/usage-test")

        assert response.status_code == 204
        assert any("Token usage" in record.message for record in caplog.records)

    def test_usage_accumulation_tracks_request_tokens(self) -> None:
        """merge helper should accumulate request token usage."""
        from streaming import merge_usage

        base = UsageDetails(input_token_count=1, output_token_count=2, total_token_count=3)
        increment = UsageDetails(input_token_count=4, output_token_count=5, total_token_count=9)

        merged = merge_usage(base, increment)

        assert _usage_value(merged, "input_token_count") == 5
        assert _usage_value(merged, "output_token_count") == 7
        assert _usage_value(merged, "total_token_count") == 12


class TestInputValidation:
    """Test that user input length is validated against configurable limits (FR-011)."""

    def test_send_message_validates_input_length(self, client) -> None:
        """send_message should reject messages exceeding the configured max length."""

        _sessions.clear()
        _sessions["long-input-test"] = _make_session("long-input-test")

        response = client.post(
            "/api/sessions/long-input-test/messages",
            json={"content": "x" * (DEFAULT_MAX_USER_INPUT_CHARS + 1)},
        )

        assert response.status_code == 400
        assert "exceeds maximum length" in response.json()["detail"]
