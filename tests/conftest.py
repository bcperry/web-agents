"""Shared test fixtures and configuration.

Sets environment variables required by the FastAPI app for testing.
"""

import os

import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def client():
	"""FastAPI TestClient with clean in-memory sessions."""
	from main import _sessions, app

	_sessions.clear()
	with TestClient(app) as test_client:
		yield test_client
	_sessions.clear()


@pytest.fixture
def skills_client(tmp_path, monkeypatch):
	"""FastAPI TestClient with skills storage redirected to a temporary directory."""
	import main as main_module
	from main import _sessions, app

	monkeypatch.setattr(main_module, "_get_skills_dir", lambda: tmp_path)
	_sessions.clear()
	with TestClient(app) as test_client:
		yield test_client, tmp_path
	_sessions.clear()


@pytest.fixture
def make_skill():
	def _make_skill(tmp_path, name: str, description: str = "A test skill", content: str = "# Content\nHello."):
		skill_dir = tmp_path / name
		skill_dir.mkdir()
		skill_file = skill_dir / "SKILL.md"
		skill_file.write_text(
			f'---\nname: {name}\ndescription: "{description}"\n---\n\n{content}\n',
			encoding="utf-8",
		)
		return skill_dir

	return _make_skill
