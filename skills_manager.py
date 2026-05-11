"""File-backed skill management helpers."""

import os
import re
import shutil
from pathlib import Path

from fastapi import HTTPException

_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SKILL_MD_TEMPLATE = '---\nname: {name}\ndescription: "{description}"\n---\n\n{content}\n'


class SkillManager:
	def __init__(self, skills_dir: Path):
		self.skills_dir = skills_dir

	def validate_name(self, name: str, status_on_error: int = 400) -> str:
		if not name or not _SKILL_NAME_RE.match(name) or len(name) > 64:
			raise HTTPException(status_code=status_on_error, detail="Invalid skill name")
		return name

	def skill_path(self, name: str, status_on_error: int = 400) -> Path:
		safe_name = self.validate_name(name, status_on_error=status_on_error)
		base_name = os.path.basename(safe_name)
		skill_path = (self.skills_dir / base_name).resolve()
		if not skill_path.is_relative_to(self.skills_dir.resolve()):
			raise HTTPException(status_code=400, detail="Invalid skill name")
		return skill_path

	def parse(self, skill_dir: Path) -> dict:
		skill_file = skill_dir / "SKILL.md"
		if not skill_dir.is_dir() or not skill_file.is_file():
			raise HTTPException(status_code=404, detail=f"Skill not found: {skill_dir.name}")
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

	def list_summaries(self) -> list[dict[str, str]]:
		if not self.skills_dir.is_dir():
			return []
		from agent_framework import SkillsProvider

		provider = SkillsProvider(skill_paths=self.skills_dir)
		return [
			{"name": skill.name, "description": skill.description}
			for skill in provider._skills.values()
		]

	def get(self, name: str) -> dict:
		return self.parse(self.skill_path(name))

	def create(self, name: str, description: str, content: str) -> dict:
		safe_name = self.validate_name(name, status_on_error=422)
		self._validate_description(description)
		self._validate_content(content)
		skill_path = self.skill_path(safe_name)
		if skill_path.exists():
			raise HTTPException(status_code=409, detail=f"Skill already exists: {safe_name}")
		skill_path.mkdir(parents=True, exist_ok=False)
		self._write_skill(skill_path, safe_name, description, content)
		return {"name": safe_name, "description": description, "content": content}

	def update(self, name: str, description: str, content: str) -> dict:
		safe_name = self.validate_name(name)
		self._validate_description(description)
		self._validate_content(content)
		skill_path = self.skill_path(safe_name)
		if not skill_path.is_dir():
			raise HTTPException(status_code=404, detail=f"Skill not found: {safe_name}")
		self._write_skill(skill_path, safe_name, description, content)
		return {"name": safe_name, "description": description, "content": content}

	def delete(self, name: str) -> None:
		safe_name = self.validate_name(name)
		skill_path = self.skill_path(safe_name)
		if not skill_path.is_dir():
			raise HTTPException(status_code=404, detail=f"Skill not found: {safe_name}")
		shutil.rmtree(skill_path)

	@staticmethod
	def _validate_description(description: str) -> None:
		if not description or len(description) > 256:
			raise HTTPException(status_code=422, detail="Description must be non-empty (max 256 chars)")

	@staticmethod
	def _validate_content(content: str) -> None:
		if not content or len(content) > 65536:
			raise HTTPException(status_code=422, detail="Content must be non-empty (max 65536 chars)")

	@staticmethod
	def _write_skill(skill_path: Path, name: str, description: str, content: str) -> None:
		safe_description = description.replace('"', '\\"')
		(skill_path / "SKILL.md").write_text(
			_SKILL_MD_TEMPLATE.format(name=name, description=safe_description, content=content),
			encoding="utf-8",
		)


__all__ = ["SkillManager"]