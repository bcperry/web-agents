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


@pytest.fixture(autouse=True)
def _cosmos_doubles(monkeypatch):
	"""Inject loop-independent in-memory Cosmos doubles for every test so the strict
	'Cosmos required' startup check passes and API tests can seed via asyncio.run and
	read via TestClient (different event loops) without a live emulator. The REAL
	Cosmos repository is covered by the emulator-backed tests in test_cosmos_memory.py.

	Uses monkeypatch (auto-reverts) so production carries no test-only injection seams."""
	import cosmos_memory
	import user_data
	from agent_framework import InMemoryHistoryProvider
	from tests._doubles import InMemoryConversationRepository, InMemoryUserScopedRepository

	monkeypatch.setattr(cosmos_memory, "_cosmos_client", None)
	monkeypatch.setattr(cosmos_memory, "_async_credential", None)
	monkeypatch.setattr(cosmos_memory, "_history_provider", InMemoryHistoryProvider(skip_excluded=True))
	monkeypatch.setattr(cosmos_memory, "_conversation_repo", InMemoryConversationRepository())
	monkeypatch.setattr(user_data, "_custom_agents_repo", InMemoryUserScopedRepository())
	monkeypatch.setattr(user_data, "_agent_customizations_repo", InMemoryUserScopedRepository())
	monkeypatch.setattr(user_data, "_user_profile_repo", InMemoryUserScopedRepository())
	yield


@pytest.fixture
def client():
	"""FastAPI TestClient with clean in-memory sessions."""
	from main import _sessions, app

	_sessions.clear()
	with TestClient(app) as test_client:
		yield test_client
	_sessions.clear()


@pytest.fixture
def cosmos_emulator(monkeypatch):
	"""Point the app at the local Azure Cosmos DB Emulator; skip if unreachable.

	Used by ``@pytest.mark.emulator`` integration tests. The well-known emulator
	key is a public, fixed value (not a secret).
	"""
	import socket
	from urllib.parse import urlsplit

	from tests._doubles import clear_cosmos_singletons

	endpoint = os.environ.get("AZURE_COSMOS_EMULATOR_ENDPOINT", "https://localhost:8081/")
	parsed = urlsplit(endpoint)
	host = parsed.hostname or "localhost"
	port = parsed.port or 8081
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	sock.settimeout(0.5)
	try:
		reachable = sock.connect_ex((host, port)) == 0
	finally:
		sock.close()
	if not reachable:
		pytest.skip(f"Azure Cosmos DB Emulator not reachable at {endpoint}")

	well_known_key = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
	monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", endpoint)
	monkeypatch.setenv("AZURE_COSMOS_KEY", os.environ.get("AZURE_COSMOS_KEY", well_known_key))
	monkeypatch.setenv("AZURE_COSMOS_DATABASE_NAME", os.environ.get("AZURE_COSMOS_DATABASE_NAME", "agent-memory-test"))
	monkeypatch.setenv("AZURE_COSMOS_CONTAINER_NAME", os.environ.get("AZURE_COSMOS_CONTAINER_NAME", "chat-history-test"))
	monkeypatch.setenv("AZURE_COSMOS_CONVERSATIONS_CONTAINER", os.environ.get("AZURE_COSMOS_CONVERSATIONS_CONTAINER", "conversations-test"))
	# Clear the autouse in-memory doubles so the REAL Cosmos providers are built.
	clear_cosmos_singletons(monkeypatch)
	yield


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
