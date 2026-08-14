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
	from tests._doubles import (
		InMemoryAgentViewRepository,
		InMemoryAutonomousLeaseRepository,
		InMemoryAutonomousRunRepository,
		InMemoryByIdRepository,
		InMemoryConversationRepository,
		InMemoryUserScopedRepository,
	)

	# Seed the directive double from the YAML defaults, mirroring the startup seed
	# in production (so directive reads return the configured directives offline).
	from autonomous import load_autonomous_config

	seed_docs = [d.to_doc() for d in load_autonomous_config().directives]

	# Seed the skill double from the filesystem defaults, mirroring the startup seed
	# in production (so skill reads return the built-in skills offline).
	from pathlib import Path

	import skills_manager

	skill_seed_docs = skills_manager.filesystem_skill_docs(
		Path(__file__).resolve().parent.parent / "skills"
	)

	monkeypatch.setattr(cosmos_memory, "_cosmos_client", None)
	monkeypatch.setattr(cosmos_memory, "_async_credential", None)
	monkeypatch.setattr(cosmos_memory, "_history_provider", InMemoryHistoryProvider(skip_excluded=True))
	monkeypatch.setattr(cosmos_memory, "_conversation_repo", InMemoryConversationRepository())
	monkeypatch.setattr(cosmos_memory, "_autonomous_run_repo", InMemoryAutonomousRunRepository())
	monkeypatch.setattr(cosmos_memory, "_autonomous_lease_repo", InMemoryAutonomousLeaseRepository())
	monkeypatch.setattr(
		cosmos_memory, "_autonomous_directive_repo", InMemoryByIdRepository(seed_docs)
	)
	monkeypatch.setattr(cosmos_memory, "_skill_repo", InMemoryByIdRepository(skill_seed_docs))
	monkeypatch.setattr(user_data, "_custom_agents_repo", InMemoryUserScopedRepository())
	monkeypatch.setattr(user_data, "_agent_customizations_repo", InMemoryUserScopedRepository())
	monkeypatch.setattr(user_data, "_user_profile_repo", InMemoryUserScopedRepository())
	monkeypatch.setattr(user_data, "_user_skills_repo", InMemoryUserScopedRepository())
	monkeypatch.setattr(user_data, "_agent_views_repo", InMemoryAgentViewRepository())
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

	endpoint = os.environ.get("AZURE_COSMOS_EMULATOR_ENDPOINT", "http://localhost:8081/")
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
	monkeypatch.setenv("AZURE_COSMOS_SKILLS_CONTAINER", os.environ.get("AZURE_COSMOS_SKILLS_CONTAINER", "skills-test"))
	# Clear the autouse in-memory doubles so the REAL Cosmos providers are built.
	clear_cosmos_singletons(monkeypatch)
	yield


@pytest.fixture
def skills_client(monkeypatch):
	"""FastAPI TestClient with an empty in-memory skill store (Cosmos double).

	The app lifespan seeds the filesystem default skills at startup, so this fixture
	resets ``_skill_repo`` to a fresh empty repository *after* startup — giving the
	skills CRUD tests a clean catalog. Yields the repo for direct seeding.
	"""
	import cosmos_memory
	from main import _sessions, app
	from tests._doubles import InMemoryByIdRepository

	_sessions.clear()
	with TestClient(app) as test_client:
		repo = InMemoryByIdRepository()
		monkeypatch.setattr(cosmos_memory, "_skill_repo", repo)
		yield test_client, repo
	_sessions.clear()


@pytest.fixture
def make_skill():
	"""Insert a skill document directly into an ``InMemoryByIdRepository`` double."""
	import asyncio
	from datetime import datetime, timezone

	def _make_skill(repo, name: str, description: str = "A test skill", content: str = "# Content\nHello."):
		now = datetime.now(timezone.utc).isoformat()
		doc = {
			"id": name,
			"description": description,
			"content": content,
			"created_at": now,
			"updated_at": now,
			"doc_type": "skill",
			"schema_version": 1,
		}
		asyncio.run(repo.upsert(doc))
		return doc

	return _make_skill
