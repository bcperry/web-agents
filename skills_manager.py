"""Cosmos-backed skill management + filesystem seeding.

Skills are global operator config authored in the admin Skill Builder. They live
durably in Azure Cosmos DB (the shared global by-id store in ``cosmos_memory``,
via ``get_skill_repository()``); the repository ``skills/`` directory is only the
SEED source of default skills. ``SkillManager`` keeps the name/description/content
validation and maps Cosmos documents to the ``{name, description, content}`` wire
shape the frontend uses.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

import cosmos_memory

_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _utcnow_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def _skill_doc(
	name: str, description: str, content: str, *, created_at: str, updated_at: str
) -> dict[str, Any]:
	return {
		"id": name,
		"description": description,
		"content": content,
		"created_at": created_at,
		"updated_at": updated_at,
		"doc_type": "skill",
		"schema_version": 1,
	}


def _parse_skill_md(skill_dir: Path) -> dict[str, str] | None:
	"""Parse a filesystem ``<skill>/SKILL.md`` into ``{name, description, content}``.

	Returns ``None`` when the directory has no ``SKILL.md`` (used only by seeding).
	"""
	skill_file = skill_dir / "SKILL.md"
	if not skill_dir.is_dir() or not skill_file.is_file():
		return None
	raw = skill_file.read_text(encoding="utf-8")
	name = skill_dir.name
	description = ""
	content = raw
	if raw.startswith("---"):
		end = raw.find("\n---", 3)
		if end != -1:
			frontmatter = raw[3:end].strip()
			content = raw[end + 4:].lstrip("\n")
			for line in frontmatter.splitlines():
				if line.startswith("description:"):
					description = line[len("description:"):].strip().strip('"').strip("'")
				elif line.startswith("name:"):
					name = line[len("name:"):].strip()
	return {"name": name, "description": description, "content": content}


class SkillManager:
	"""Validation + Cosmos CRUD for global agent skills.

	Construct with no arguments in request handlers (it uses the shared Cosmos
	skill repository); pass an explicit ``repo`` in tests to inject a double.
	"""

	def __init__(self, repo: Any = None) -> None:
		self._repo = repo

	def _repository(self) -> Any:
		return self._repo if self._repo is not None else cosmos_memory.get_skill_repository()

	def validate_name(self, name: str, status_on_error: int = 400) -> str:
		if not name or not _SKILL_NAME_RE.match(name) or len(name) > 64:
			raise HTTPException(status_code=status_on_error, detail="Invalid skill name")
		return name

	async def list_summaries(self) -> list[dict[str, str]]:
		docs = await self._repository().list_all()
		return [
			{"name": d["id"], "description": str(d.get("description") or "")}
			for d in docs
		]

	async def get(self, name: str) -> dict[str, str]:
		safe_name = self.validate_name(name)
		doc = await self._repository().get(safe_name)
		if not doc:
			raise HTTPException(status_code=404, detail=f"Skill not found: {safe_name}")
		return {
			"name": doc["id"],
			"description": str(doc.get("description") or ""),
			"content": str(doc.get("content") or ""),
		}

	async def create(self, name: str, description: str, content: str) -> dict[str, str]:
		from azure.cosmos.exceptions import CosmosResourceExistsError

		safe_name = self.validate_name(name, status_on_error=422)
		self._validate_description(description)
		self._validate_content(content)
		now = _utcnow_iso()
		doc = _skill_doc(safe_name, description, content, created_at=now, updated_at=now)
		try:
			await self._repository().create(doc)
		except CosmosResourceExistsError:
			raise HTTPException(status_code=409, detail=f"Skill already exists: {safe_name}")
		return {"name": safe_name, "description": description, "content": content}

	async def update(self, name: str, description: str, content: str) -> dict[str, str]:
		safe_name = self.validate_name(name)
		self._validate_description(description)
		self._validate_content(content)
		repo = self._repository()
		existing = await repo.get(safe_name)
		if not existing:
			raise HTTPException(status_code=404, detail=f"Skill not found: {safe_name}")
		created_at = str(existing.get("created_at") or _utcnow_iso())
		doc = _skill_doc(
			safe_name, description, content, created_at=created_at, updated_at=_utcnow_iso()
		)
		await repo.upsert(doc)
		return {"name": safe_name, "description": description, "content": content}

	async def delete(self, name: str) -> None:
		safe_name = self.validate_name(name)
		deleted = await self._repository().delete(safe_name)
		if not deleted:
			raise HTTPException(status_code=404, detail=f"Skill not found: {safe_name}")

	@staticmethod
	def _validate_description(description: str) -> None:
		if not description or len(description) > 256:
			raise HTTPException(
				status_code=422, detail="Description must be non-empty (max 256 chars)"
			)

	@staticmethod
	def _validate_content(content: str) -> None:
		if not content or len(content) > 65536:
			raise HTTPException(
				status_code=422, detail="Content must be non-empty (max 65536 chars)"
			)


async def seed_skills(skills_dir: Path) -> int:
	"""Seed filesystem default skills into Cosmos for any id not already present.

	Idempotent (runs at startup): existing — possibly edited — skills are left
	untouched so runtime edits persist; brand-new filesystem defaults are added. A
	default deleted at runtime reappears on the next startup (it is a default);
	remove it from ``skills/`` to retire it permanently. Mirrors
	``autonomous.seed_autonomous_directives``.
	"""
	defaults = filesystem_skill_docs(skills_dir)
	if not defaults:
		return 0
	repo = cosmos_memory.get_skill_repository()
	existing = {str(doc.get("id")) for doc in await repo.list_all()}
	seeded = 0
	for doc in defaults:
		if doc["id"] in existing:
			continue
		await repo.upsert(doc)
		seeded += 1
	return seeded


def filesystem_skill_docs(skills_dir: Path) -> list[dict[str, Any]]:
	"""Return durable skill documents parsed from the filesystem default skills.

	Shared by ``seed_skills`` (production startup) and the test fixtures so the
	in-memory double is seeded with the same built-in skills the real store gets.
	Skips directories without a valid ``SKILL.md`` / name / content.
	"""
	if not skills_dir.is_dir():
		return []
	now = _utcnow_iso()
	docs: list[dict[str, Any]] = []
	for child in sorted(skills_dir.iterdir()):
		parsed = _parse_skill_md(child)
		if (
			parsed
			and parsed.get("name")
			and parsed.get("description")
			and parsed.get("content")
			and _SKILL_NAME_RE.match(parsed["name"])
		):
			docs.append(
				_skill_doc(
					parsed["name"],
					parsed.get("description", ""),
					parsed["content"],
					created_at=now,
					updated_at=now,
				)
			)
	return docs


__all__ = ["SkillManager", "seed_skills", "filesystem_skill_docs"]
