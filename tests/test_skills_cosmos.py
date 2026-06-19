"""Skill durability tests: seeding (offline doubles) + real Cosmos repo (emulator).

The offline tests use the in-memory ``InMemoryByIdRepository`` double; the
``@pytest.mark.emulator`` test exercises the real ``_CosmosByIdRepository`` (via
``get_skill_repository()``) against the local Azure Cosmos DB Emulator and is
auto-skipped when it is unreachable.
"""

import asyncio
from uuid import uuid4

import pytest

from tests._doubles import InMemoryByIdRepository


def _write_fs_skill(base, name, description="A skill", content="# Body"):
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: "{description}"\n---\n\n{content}\n',
        encoding="utf-8",
    )
    return skill_dir


# ---------------------------------------------------------------------------
# US4 — seeding from the filesystem defaults (idempotent, non-destructive)
# ---------------------------------------------------------------------------

def test_seed_skills_populates_empty_store(monkeypatch, tmp_path):
    import cosmos_memory
    from skills_manager import seed_skills

    _write_fs_skill(tmp_path, "fs-alpha", "Alpha desc", "# Alpha")
    _write_fs_skill(tmp_path, "fs-beta", "Beta desc", "# Beta")

    repo = InMemoryByIdRepository()
    monkeypatch.setattr(cosmos_memory, "_skill_repo", repo)

    seeded = asyncio.run(seed_skills(tmp_path))
    assert seeded == 2
    ids = {d["id"] for d in asyncio.run(repo.list_all())}
    assert ids == {"fs-alpha", "fs-beta"}

    # Idempotent: a second seed adds nothing.
    assert asyncio.run(seed_skills(tmp_path)) == 0


def test_seed_skills_preserves_existing_edits(monkeypatch, tmp_path):
    import cosmos_memory
    from skills_manager import seed_skills

    _write_fs_skill(tmp_path, "fs-alpha", "Original desc", "# Original")
    repo = InMemoryByIdRepository()
    monkeypatch.setattr(cosmos_memory, "_skill_repo", repo)

    # An operator-edited version is already durable in the store.
    asyncio.run(repo.upsert({
        "id": "fs-alpha",
        "description": "Edited",
        "content": "# Edited",
        "created_at": "2020-01-01T00:00:00+00:00",
        "updated_at": "2020-01-01T00:00:00+00:00",
        "doc_type": "skill",
        "schema_version": 1,
    }))

    seeded = asyncio.run(seed_skills(tmp_path))
    assert seeded == 0  # the existing id is not overwritten
    doc = asyncio.run(repo.get("fs-alpha"))
    assert doc["content"] == "# Edited"


def test_seed_skills_adds_only_new_defaults(monkeypatch, tmp_path):
    import cosmos_memory
    from skills_manager import seed_skills

    _write_fs_skill(tmp_path, "fs-alpha", "Alpha", "# Alpha")
    repo = InMemoryByIdRepository()
    monkeypatch.setattr(cosmos_memory, "_skill_repo", repo)
    assert asyncio.run(seed_skills(tmp_path)) == 1

    # A brand-new repo default appears on the next startup; existing is untouched.
    _write_fs_skill(tmp_path, "fs-gamma", "Gamma", "# Gamma")
    assert asyncio.run(seed_skills(tmp_path)) == 1
    ids = {d["id"] for d in asyncio.run(repo.list_all())}
    assert ids == {"fs-alpha", "fs-gamma"}


# ---------------------------------------------------------------------------
# US1 — durability across "restart" (a fresh manager over the same durable store)
# ---------------------------------------------------------------------------

def test_skill_persists_across_manager_instances():
    from skills_manager import SkillManager

    durable_store = InMemoryByIdRepository()
    asyncio.run(SkillManager(durable_store).create("durable", "Survives", "# Durable body"))

    # A fresh SkillManager (simulating a restarted process) over the SAME durable
    # store still reads the skill — it was never on process-local disk.
    fresh = SkillManager(durable_store)
    got = asyncio.run(fresh.get("durable"))
    assert got == {"name": "durable", "description": "Survives", "content": "# Durable body"}


# ---------------------------------------------------------------------------
# US5 — real Cosmos skill store CRUD via the emulator
# ---------------------------------------------------------------------------

@pytest.mark.emulator
def test_cosmos_skill_repository_crud(cosmos_emulator):
    import cosmos_memory

    async def scenario():
        repo = cosmos_memory.get_skill_repository()
        skill_id = f"emu-skill-{uuid4().hex[:8]}"
        now = "2026-06-19T00:00:00+00:00"
        doc = {
            "id": skill_id,
            "description": "Emulator skill",
            "content": "# Emulator\nBody.",
            "created_at": now,
            "updated_at": now,
            "doc_type": "skill",
            "schema_version": 1,
        }
        try:
            await repo.create(doc)

            got = await repo.get(skill_id)
            assert got is not None
            assert got["description"] == "Emulator skill"

            listed = {d["id"] for d in await repo.list_all()}
            assert skill_id in listed

            # Atomic create conflicts on a duplicate id.
            from azure.cosmos.exceptions import CosmosResourceExistsError

            with pytest.raises(CosmosResourceExistsError):
                await repo.create(doc)

            updated = dict(doc, description="Updated", content="# Updated")
            await repo.upsert(updated)
            assert (await repo.get(skill_id))["description"] == "Updated"

            assert await repo.delete(skill_id) is True
            assert await repo.get(skill_id) is None
        finally:
            await repo.delete(skill_id)
            await cosmos_memory.close_cosmos()

    asyncio.run(scenario())
