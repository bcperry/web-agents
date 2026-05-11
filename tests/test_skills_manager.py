"""Tests for file-backed skill management."""

import pytest
from fastapi import HTTPException

from skills_manager import SkillManager


def test_list_and_get_skills(tmp_path, make_skill):
    make_skill(tmp_path, "alpha", "Alpha skill", "# Alpha\nBody")
    manager = SkillManager(tmp_path)

    assert manager.list_summaries() == [{"name": "alpha", "description": "Alpha skill"}]
    assert manager.get("alpha") == {"name": "alpha", "description": "Alpha skill", "content": "# Alpha\nBody\n"}


def test_create_update_and_delete_skill(tmp_path):
    manager = SkillManager(tmp_path)

    created = manager.create("new-skill", "A new skill", "# Body")
    assert created == {"name": "new-skill", "description": "A new skill", "content": "# Body"}
    assert (tmp_path / "new-skill" / "SKILL.md").is_file()

    updated = manager.update("new-skill", "Updated", "# Updated")
    assert updated == {"name": "new-skill", "description": "Updated", "content": "# Updated"}

    manager.delete("new-skill")
    assert not (tmp_path / "new-skill").exists()


def test_skill_manager_errors_match_api_contract(tmp_path, make_skill):
    manager = SkillManager(tmp_path)
    make_skill(tmp_path, "existing")

    with pytest.raises(HTTPException) as invalid:
        manager.create("Bad-Name", "desc", "body")
    assert invalid.value.status_code == 422

    with pytest.raises(HTTPException) as duplicate:
        manager.create("existing", "desc", "body")
    assert duplicate.value.status_code == 409

    with pytest.raises(HTTPException) as missing:
        manager.get("missing")
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as traversal:
        manager.skill_path("../etc")
    assert traversal.value.status_code == 400