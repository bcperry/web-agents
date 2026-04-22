"""Shared test fixtures and configuration.

Sets environment variables required by the FastAPI app for testing.
"""

import os

# Auth disabled for tests by default
os.environ.setdefault("AUTH_DISABLED", "true")
# Set a dummy SQL connection string to avoid startup errors (won't actually connect)
os.environ.setdefault("AZURE_SQL_CONNECTIONSTRING", "")
# Set dummy Azure AI Search env vars for semantic_search tool validation (won't actually connect)
os.environ.setdefault("SEARCH_SERVICE_ENDPOINT", "https://test.search.windows.net")
os.environ.setdefault("SEARCH_INDEX_NAME", "test-index")
# Set dummy Azure OpenAI env vars for client construction (won't actually connect)
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.us")
os.environ.setdefault("AZURE_OPENAI_MODEL", "gpt-4o")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
