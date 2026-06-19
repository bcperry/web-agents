"""Tests for the Cosmos-backed SkillManager."""

import asyncio

import pytest
from fastapi import HTTPException

from skills_manager import SkillManager
from tests._doubles import InMemoryByIdRepository


def test_list_and_get_skills(make_skill):
    repo = InMemoryByIdRepository()
    make_skill(repo, "alpha", "Alpha skill", "# Alpha\nBody")
    manager = SkillManager(repo)

    assert asyncio.run(manager.list_summaries()) == [{"name": "alpha", "description": "Alpha skill"}]
    assert asyncio.run(manager.get("alpha")) == {
        "name": "alpha",
        "description": "Alpha skill",
        "content": "# Alpha\nBody",
    }


def test_create_update_and_delete_skill():
    repo = InMemoryByIdRepository()
    manager = SkillManager(repo)

    created = asyncio.run(manager.create("new-skill", "A new skill", "# Body"))
    assert created == {"name": "new-skill", "description": "A new skill", "content": "# Body"}
    assert asyncio.run(repo.get("new-skill")) is not None

    updated = asyncio.run(manager.update("new-skill", "Updated", "# Updated"))
    assert updated == {"name": "new-skill", "description": "Updated", "content": "# Updated"}

    asyncio.run(manager.delete("new-skill"))
    assert asyncio.run(repo.get("new-skill")) is None


def test_update_preserves_created_at():
    repo = InMemoryByIdRepository()
    manager = SkillManager(repo)

    asyncio.run(manager.create("keep", "desc", "# v1"))
    original = asyncio.run(repo.get("keep"))["created_at"]

    asyncio.run(manager.update("keep", "desc-2", "# v2"))
    after = asyncio.run(repo.get("keep"))
    assert after["created_at"] == original
    assert after["updated_at"] >= original


def test_skill_manager_errors_match_api_contract(make_skill):
    repo = InMemoryByIdRepository()
    make_skill(repo, "existing")
    manager = SkillManager(repo)

    with pytest.raises(HTTPException) as invalid:
        asyncio.run(manager.create("Bad-Name", "desc", "body"))
    assert invalid.value.status_code == 422

    with pytest.raises(HTTPException) as duplicate:
        asyncio.run(manager.create("existing", "desc", "body"))
    assert duplicate.value.status_code == 409

    with pytest.raises(HTTPException) as missing:
        asyncio.run(manager.get("missing"))
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as bad_update:
        asyncio.run(manager.update("missing", "desc", "body"))
    assert bad_update.value.status_code == 404

    with pytest.raises(HTTPException) as bad_delete:
        asyncio.run(manager.delete("missing"))
    assert bad_delete.value.status_code == 404


def test_validation_rejects_empty_and_oversized_fields():
    manager = SkillManager(InMemoryByIdRepository())

    with pytest.raises(HTTPException) as empty_desc:
        asyncio.run(manager.create("ok-name", "", "body"))
    assert empty_desc.value.status_code == 422

    with pytest.raises(HTTPException) as big_desc:
        asyncio.run(manager.create("ok-name", "d" * 257, "body"))
    assert big_desc.value.status_code == 422

    with pytest.raises(HTTPException) as empty_content:
        asyncio.run(manager.create("ok-name", "desc", ""))
    assert empty_content.value.status_code == 422
