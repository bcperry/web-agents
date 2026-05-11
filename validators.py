"""Validation helpers for request, tool, skill, and image handling."""

from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_SIZE_BYTES = 400 * 1024 * 1024
MAX_IMAGES_PER_MESSAGE = 5

_MAGIC_BYTES: dict[str, list[bytes]] = {
	"image/jpeg": [b"\xff\xd8\xff"],
	"image/png": [b"\x89PNG\r\n\x1a\n"],
	"image/gif": [b"GIF87a", b"GIF89a"],
	"image/webp": [],
}


def validate_image_magic_bytes(data: bytes, claimed_mime: str) -> bool:
	if not data:
		return False
	if claimed_mime == "image/webp":
		return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
	signatures = _MAGIC_BYTES.get(claimed_mime, [])
	return any(data[: len(signature)] == signature for signature in signatures)


def validate_uploaded_images(files: list[UploadFile], file_data: list[bytes]) -> Optional[str]:
	if len(files) > MAX_IMAGES_PER_MESSAGE:
		return f"Maximum of {MAX_IMAGES_PER_MESSAGE} images per message. Please reduce the number of images."

	for uploaded_file, data in zip(files, file_data):
		mime = uploaded_file.content_type or ""
		name = uploaded_file.filename or "uploaded file"

		if mime not in ALLOWED_IMAGE_MIMES:
			return (
				"Only image files are accepted (JPEG, PNG, GIF, WebP). "
				f"'{name}' is not a supported image type."
			)

		if len(data) > MAX_IMAGE_SIZE_BYTES:
			return f"'{name}' exceeds the maximum file size of 400 MB."

		if not validate_image_magic_bytes(data, mime):
			return f"'{name}' could not be processed. The file may be corrupt or unreadable."

	return None


def validate_temperature(raw_temperature: object, field_name: str = "custom_temperature") -> float | None:
	if raw_temperature is None:
		return None
	try:
		temperature = float(raw_temperature)
	except (TypeError, ValueError):
		raise HTTPException(status_code=400, detail=f"{field_name} must be a number")
	if not (0.0 <= temperature <= 2.0):
		raise HTTPException(status_code=400, detail=f"{field_name} must be between 0.0 and 2.0")
	return temperature


def validate_custom_name(value: object) -> str:
	custom_name = str(value or "").strip()
	if not custom_name or len(custom_name) > 100:
		raise HTTPException(status_code=400, detail="custom_name is required and must be <= 100 characters")
	return custom_name


def validate_prompt(value: object, *, max_chars: int, field_name: str = "custom_prompt") -> str:
	prompt = str(value or "").strip()
	if not prompt or len(prompt) > max_chars:
		raise HTTPException(status_code=400, detail=f"{field_name} is required and must be <= {max_chars} characters")
	return prompt


def known_tool_names_from_profiles(profiles_data: dict) -> set[str]:
	known_tools: set[str] = {"get_user_profile", "save_user_profile"}
	for entry in profiles_data.values():
		if isinstance(entry, dict):
			for tool_name in entry.get("tools") or []:
				if isinstance(tool_name, str):
					known_tools.add(tool_name)
	return known_tools


def validate_tool_names(raw_tools: object, known_tools: set[str], field_name: str = "custom_tools") -> list[str]:
	if not isinstance(raw_tools, list):
		raise HTTPException(status_code=400, detail=f"{field_name} must be a list of tool name strings")
	invalid_tools = [tool_name for tool_name in raw_tools if tool_name not in known_tools]
	if invalid_tools:
		raise HTTPException(status_code=400, detail=f"Unknown tools: {', '.join(invalid_tools)}")
	return list(raw_tools)


def available_skill_names(skills_dir: Path) -> set[str]:
	if not skills_dir.is_dir():
		return set()
	from agent_framework import SkillsProvider

	provider = SkillsProvider(skill_paths=skills_dir)
	return set(provider._skills.keys())


def filter_known_skill_names(raw_skills: object, available_skills: set[str], field_name: str = "custom_skills") -> tuple[list[str], list[str]]:
	if not isinstance(raw_skills, list):
		raise HTTPException(status_code=400, detail=f"{field_name} must be a list of skill name strings")
	known = [name for name in raw_skills if name in available_skills]
	dropped = [name for name in raw_skills if name not in available_skills]
	return known, dropped


def validate_http_mcp_servers(raw_servers: object, *, override: bool) -> list[dict]:
	if not isinstance(raw_servers, list):
		raise HTTPException(status_code=400, detail="mcp_servers must be a list")

	for entry in raw_servers:
		if not isinstance(entry, dict):
			raise HTTPException(status_code=400, detail="Each mcp_servers entry must be an object")
		if not entry.get("name"):
			raise HTTPException(status_code=400, detail="Each mcp_servers entry requires a 'name'")
		if entry.get("transport") != "http":
			if override:
				raise HTTPException(status_code=400, detail="Built-in profile overrides only support 'http' MCP servers")
			raise HTTPException(
				status_code=400,
				detail="Custom agents only support 'http' MCP servers. Local (stdio) servers must be configured in agents.yaml.",
			)
		if not entry.get("url"):
			raise HTTPException(status_code=400, detail=f"MCP server '{entry['name']}' (http) requires a 'url'")

	return raw_servers


__all__ = [
	"ALLOWED_IMAGE_MIMES",
	"MAX_IMAGE_SIZE_BYTES",
	"MAX_IMAGES_PER_MESSAGE",
	"available_skill_names",
	"filter_known_skill_names",
	"known_tool_names_from_profiles",
	"validate_custom_name",
	"validate_http_mcp_servers",
	"validate_image_magic_bytes",
	"validate_prompt",
	"validate_temperature",
	"validate_tool_names",
	"validate_uploaded_images",
]