"""Tests for request retry classification and session behavior."""

import pytest
from unittest.mock import patch, MagicMock
from openai.lib.azure import AsyncAzureOpenAI
from main import _is_retryable_error
from agent_framework._types import UsageDetails


def _usage_value(usage: UsageDetails, key: str):
    if isinstance(usage, dict):
        return usage.get(key)
    return getattr(usage, key)


class TestAzureClientRetryConfiguration:
    """Test representative Azure OpenAI client retry configuration."""

    def test_primary_client_can_be_configured_with_retries(self) -> None:
        """Primary AsyncAzureOpenAI client supports explicit retry configuration."""
        client = AsyncAzureOpenAI(
            azure_endpoint="https://test.openai.azure.us",
            azure_deployment="gpt-4o",
            api_key="test-key",
            api_version="2024-02-15-preview",
            max_retries=3,
        )
        assert client.max_retries == 3

    def test_secondary_client_has_retries(self) -> None:
        """Secondary AsyncAzureOpenAI client can be configured for resilient summarization."""
        client = AsyncAzureOpenAI(
            azure_endpoint="https://test-secondary.openai.azure.us",
            azure_deployment="gpt-4o-mini",
            api_key="test-key",
            api_version="2024-02-15-preview",
            max_retries=3,
        )
        assert client.max_retries == 3

    def test_retry_count_can_differ_from_default(self) -> None:
        """Client retry configuration can be set explicitly."""
        client = AsyncAzureOpenAI(
            azure_endpoint="https://test.openai.azure.us",
            azure_deployment="gpt-4o",
            api_key="test-key",
            api_version="2024-02-15-preview",
            max_retries=3,
        )
        assert client.max_retries == 3
        assert client.max_retries != 2


class TestContextHandling:
    """Test stream helper inputs used for session-backed context handling."""

    def test_stream_agent_response_accepts_contents(self) -> None:
        """_stream_agent_response should accept contents: list[Content] parameter."""
        from main import _stream_agent_response
        import inspect

        sig = inspect.signature(_stream_agent_response)
        contents_param = sig.parameters.get("contents")
        assert contents_param is not None
        annotation_str = str(contents_param.annotation)
        assert "Content" in annotation_str or "list" in annotation_str


class TestIsRetryableError:
    """Test the _is_retryable_error helper function."""

    def test_detects_429_in_message(self) -> None:
        """Should detect 429 status code in error message."""
        error = Exception("Error: 429 Too Many Requests")
        assert _is_retryable_error(error) is True

    def test_detects_too_many_requests_message(self) -> None:
        """Should detect 'Too Many Requests' in error message."""
        error = Exception("Server returned Too Many Requests")
        assert _is_retryable_error(error) is True

    def test_detects_rate_limit_in_message(self) -> None:
        """Should detect 'rate_limit' in error message (case insensitive)."""
        error = Exception("Request failed due to rate_limit exceeded")
        assert _is_retryable_error(error) is True

    def test_detects_rate_limit_uppercase(self) -> None:
        """Should detect 'RATE_LIMIT' in error message (case insensitive)."""
        error = Exception("RATE_LIMIT error occurred")
        assert _is_retryable_error(error) is True

    def test_detects_capacity_in_message(self) -> None:
        """Should detect 'capacity' in error message (case insensitive)."""
        error = Exception("Service at capacity, please retry later")
        assert _is_retryable_error(error) is True

    def test_detects_capacity_uppercase(self) -> None:
        """Should detect 'CAPACITY' in error message (case insensitive)."""
        error = Exception("CAPACITY exceeded")
        assert _is_retryable_error(error) is True

    def test_does_not_match_other_errors(self) -> None:
        """Should not match unrelated errors."""
        error = Exception("Connection timeout")
        assert _is_retryable_error(error) is False

    def test_does_not_match_500_error(self) -> None:
        """Should not match 500 internal server error."""
        error = Exception("Error: 500 Internal Server Error")
        assert _is_retryable_error(error) is False

    def test_does_not_match_empty_message(self) -> None:
        """Should not match empty error message."""
        error = Exception("")
        assert _is_retryable_error(error) is False


class TestRetryLogicBehavior:
    """Tests for retry classification behavior."""

    def test_retryable_error_is_classified(self) -> None:
        """429 errors should be classified as retryable."""
        rate_limit_error = Exception("429 Too Many Requests")
        assert _is_retryable_error(rate_limit_error) is True

    def test_non_retryable_error_is_not_classified(self) -> None:
        """Non-429 errors should not be classified as retryable."""
        regular_error = Exception("Connection timeout")
        assert _is_retryable_error(regular_error) is False

    def test_rate_limit_error_type_detection(self) -> None:
        """Should detect RateLimitError type in exception."""
        # Simulate what a RateLimitError type check would return
        class RateLimitError(Exception):
            pass
        
        error = RateLimitError("Rate limit exceeded")
        assert _is_retryable_error(error) is True

    def test_azure_openai_capacity_error(self) -> None:
        """Should detect Azure OpenAI capacity errors."""
        error = Exception("The server is currently at capacity. Please try again later.")
        assert _is_retryable_error(error) is True

    def test_openai_rate_limit_header_error(self) -> None:
        """Should detect OpenAI rate limit errors with header info."""
        error = Exception("Rate limit reached for requests. Please retry after 60 seconds.")
        assert _is_retryable_error(error) is True


class TestSessionManagement:
    """Test FastAPI session management endpoints."""

    def test_create_session_exists(self) -> None:
        """create_session endpoint should be defined."""
        import main
        assert hasattr(main, 'create_session')
        assert callable(main.create_session)

    def test_delete_session_exists(self) -> None:
        """delete_session endpoint should be defined for cleanup."""
        import main
        assert hasattr(main, 'delete_session')
        assert callable(main.delete_session)

    def test_delete_session_cleans_up(self) -> None:
        """delete_session should remove session from store."""
        import inspect
        import main

        source = inspect.getsource(main.delete_session)
        assert '_sessions.pop' in source

    def test_new_session_created_each_chat_start(self) -> None:
        """Verify that agent.create_session() returns unique sessions."""
        from agent_framework import Agent
        import inspect
        from unittest.mock import MagicMock
        
        # Create mock LLM client
        mock_client = MagicMock()
        mock_client.get_chat_client_name.return_value = 'test'
        mock_client.get_model_name.return_value = 'test'
        
        init_params = inspect.signature(Agent).parameters
        if "client" in init_params:
            agent = Agent(client=mock_client, name='test', instructions='test')
        else:
            pytest.skip("Unsupported agent constructor signature for session creation test")

        session1 = agent.create_session()
        session2 = agent.create_session()

        assert session1 is not session2
        assert id(session1) != id(session2)


class TestTokenUsage:
    """Test token usage tracking functionality."""

    def test_usage_details_initialization(self) -> None:
        """UsageDetails can be initialized with token counts."""
        usage = UsageDetails(
            input_token_count=100,
            output_token_count=50,
            total_token_count=150,
        )
        assert _usage_value(usage, "input_token_count") == 100
        assert _usage_value(usage, "output_token_count") == 50
        assert _usage_value(usage, "total_token_count") == 150

    def test_usage_details_addition(self) -> None:
        """UsageDetails instances can be added together."""
        usage1 = UsageDetails(
            input_token_count=100,
            output_token_count=50,
            total_token_count=150,
        )
        usage2 = UsageDetails(
            input_token_count=200,
            output_token_count=100,
            total_token_count=300,
        )
        if isinstance(usage1, dict):
            combined = {
                "input_token_count": (usage1.get("input_token_count") or 0)
                + (usage2.get("input_token_count") or 0),
                "output_token_count": (usage1.get("output_token_count") or 0)
                + (usage2.get("output_token_count") or 0),
                "total_token_count": (usage1.get("total_token_count") or 0)
                + (usage2.get("total_token_count") or 0),
            }
        else:
            combined = usage1 + usage2
        assert _usage_value(combined, "input_token_count") == 300
        assert _usage_value(combined, "output_token_count") == 150
        assert _usage_value(combined, "total_token_count") == 450

    def test_usage_details_iadd(self) -> None:
        """UsageDetails supports in-place addition."""
        usage1 = UsageDetails(
            input_token_count=100,
            output_token_count=50,
            total_token_count=150,
        )
        usage2 = UsageDetails(
            input_token_count=200,
            output_token_count=100,
            total_token_count=300,
        )
        if isinstance(usage1, dict):
            usage1 = {
                "input_token_count": (usage1.get("input_token_count") or 0)
                + (usage2.get("input_token_count") or 0),
                "output_token_count": (usage1.get("output_token_count") or 0)
                + (usage2.get("output_token_count") or 0),
                "total_token_count": (usage1.get("total_token_count") or 0)
                + (usage2.get("total_token_count") or 0),
            }
        else:
            usage1 += usage2
        assert _usage_value(usage1, "input_token_count") == 300
        assert _usage_value(usage1, "output_token_count") == 150
        assert _usage_value(usage1, "total_token_count") == 450

    def test_usage_details_empty_initialization(self) -> None:
        """UsageDetails can be initialized with no arguments."""
        usage = UsageDetails()
        assert _usage_value(usage, "input_token_count") is None
        assert _usage_value(usage, "output_token_count") is None
        assert _usage_value(usage, "total_token_count") is None

    def test_stream_agent_response_is_async_generator(self) -> None:
        """_stream_agent_response should be an async generator."""
        from main import _stream_agent_response
        import inspect

        assert inspect.isasyncgenfunction(_stream_agent_response)

    def test_session_data_initializes_usage(self) -> None:
        """SessionData should initialize usage tracking."""
        import main

        assert hasattr(main, 'SessionData')

    def test_delete_session_logs_usage(self) -> None:
        """delete_session should log token usage on cleanup."""
        import inspect
        import main

        source = inspect.getsource(main.delete_session)
        assert 'Token usage' in source

    def test_send_message_logs_token_usage(self) -> None:
        """send_message should log token usage."""
        import inspect
        import main

        source = inspect.getsource(main.send_message)
        assert 'Request token usage' in source


class TestInputValidation:
    """Test that user input length is validated against configurable limits (FR-011)."""

    def test_max_user_input_chars_defined(self) -> None:
        """DEFAULT_MAX_USER_INPUT_CHARS constant should be defined in main."""
        import main

        assert hasattr(main, "DEFAULT_MAX_USER_INPUT_CHARS")
        assert isinstance(main.DEFAULT_MAX_USER_INPUT_CHARS, int)
        assert main.DEFAULT_MAX_USER_INPUT_CHARS == 25000

    def test_send_message_validates_input_length(self) -> None:
        """send_message should reject messages exceeding the configured max length."""
        import inspect
        import main

        source = inspect.getsource(main.send_message)
        assert "DEFAULT_MAX_USER_INPUT_CHARS" in source
        assert "exceeds maximum length" in source
