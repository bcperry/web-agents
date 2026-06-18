"""Validation helpers for request, tool, skill, and image handling."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

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


async def available_skill_names(skills_dir: Path) -> set[str]:
	if not skills_dir.is_dir():
		return set()
	from agent_framework import FileSkillsSource

	skills = await FileSkillsSource(skills_dir).get_skills()
	return {skill.frontmatter.name for skill in skills}


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


# ---------------------------------------------------------------------------
# Sub-agent tool reference validation (feature 008-agents-as-tools)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubAgentRefValidationError:
	"""A single validation failure for an agents_as_tools entry.

	Shape mirrors the wire ``details`` array in
	specs/008-agents-as-tools/contracts/api-changes.md.
	"""
	field: str
	code: str
	message: str

	def to_dict(self) -> dict[str, str]:
		return {"field": self.field, "code": self.code, "message": self.message}


def _agent_ref_target_id(agent_ref: Any) -> tuple[str, str]:
	"""Return ``(kind, target_id)`` for an AgentRef-like object or mapping.

	Accepts both the dataclass form (``BuiltinAgentRef`` / ``CustomAgentRef``)
	and the raw payload mapping the API receives. Returns ``("", "")`` for
	unrecognised shapes so the caller can surface ``unresolved_agent_ref``.
	"""
	if agent_ref is None:
		return "", ""
	# Dataclass instances
	kind = getattr(agent_ref, "kind", None)
	if kind == "builtin":
		return "builtin", str(getattr(agent_ref, "profile_id", "") or "")
	if kind == "custom":
		return "custom", str(getattr(agent_ref, "custom_agent_id", "") or "")
	# Raw mapping (frontend payload)
	if isinstance(agent_ref, dict):
		raw_kind = agent_ref.get("kind")
		if raw_kind == "builtin":
			return "builtin", str(agent_ref.get("profile_id") or agent_ref.get("profileId") or "")
		if raw_kind == "custom":
			return "custom", str(
				agent_ref.get("custom_agent_id") or agent_ref.get("customAgentId") or ""
			)
	return "", ""


def validate_sub_agent_tool_refs(
	parent_id: str,
	refs: list[Any],
	resolve_target: Callable[[str, str], Optional[Any]],
) -> list[SubAgentRefValidationError]:
	"""Validate an ``agents_as_tools`` collection.

	Parameters
	----------
	parent_id:
		Stable identifier of the agent being saved/loaded. Used for V2
		(self-reference) and V3 (direct cycle) checks.
	refs:
		The list of sub-agent tool references on the parent. Each entry may
		be a ``SubAgentToolRef`` dataclass or a raw mapping with an
		``agent_ref`` key — both shapes are accepted.
	resolve_target:
		Callable ``(kind, target_id) -> target_definition_or_None``.

		The returned target definition is used both to detect
		``unresolved_agent_ref`` (when None) and to inspect the target's own
		``agents_as_tools`` for direct A↔B cycle detection. The callback is
		expected to return either a dict-like object with an
		``agents_as_tools`` (or ``agentsAsTools``) field, or any object that
		exposes that attribute. Anything else is treated as "no sub-agents".

	Returns a list of ``SubAgentRefValidationError`` — empty on success.
	The caller is responsible for converting to an HTTPException when used
	in an API handler.
	"""
	errors: list[SubAgentRefValidationError] = []
	seen_targets: set[tuple[str, str]] = set()

	for index, raw in enumerate(refs):
		field_prefix = f"agentsAsTools[{index}]"

		# Extract agent_ref (accept dataclass or mapping)
		if hasattr(raw, "agent_ref"):
			agent_ref = raw.agent_ref
		elif isinstance(raw, dict):
			agent_ref = raw.get("agent_ref") or raw.get("agentRef")
		else:
			errors.append(SubAgentRefValidationError(
				field=field_prefix,
				code="unresolved_agent_ref",
				message="Sub-agent reference must include an agent_ref.",
			))
			continue

		kind, target_id = _agent_ref_target_id(agent_ref)
		if not kind or not target_id:
			errors.append(SubAgentRefValidationError(
				field=f"{field_prefix}.agentRef",
				code="unresolved_agent_ref",
				message="Sub-agent reference is missing a recognised target identifier.",
			))
			continue

		# V5: definition_id_mismatch (custom only)
		if kind == "custom":
			definition = None
			if isinstance(agent_ref, dict):
				definition = agent_ref.get("definition")
			else:
				definition = getattr(agent_ref, "definition", None)
			if isinstance(definition, dict):
				def_id = definition.get("id")
				if def_id is not None and str(def_id) != target_id:
					errors.append(SubAgentRefValidationError(
						field=f"{field_prefix}.agentRef.definition.id",
						code="definition_id_mismatch",
						message=(
							f"Inlined custom-agent definition id {def_id!r} "
							f"does not match customAgentId {target_id!r}."
						),
					))
					continue

		# V2: self_reference
		if parent_id and target_id == parent_id:
			errors.append(SubAgentRefValidationError(
				field=f"{field_prefix}.agentRef",
				code="self_reference",
				message="An agent cannot reference itself as a tool.",
			))
			continue

		# V4: duplicate_target
		key = (kind, target_id)
		if key in seen_targets:
			errors.append(SubAgentRefValidationError(
				field=f"{field_prefix}.agentRef",
				code="duplicate_target",
				message=f"Sub-agent {target_id!r} is referenced more than once.",
			))
			continue
		seen_targets.add(key)

		# Resolve target for V1 + V3
		target = resolve_target(kind, target_id)
		if target is None:
			errors.append(SubAgentRefValidationError(
				field=f"{field_prefix}.agentRef",
				code="unresolved_agent_ref",
				message=f"Sub-agent {target_id!r} could not be resolved.",
			))
			continue

		# V3: direct_cycle — does target reference parent_id back?
		if parent_id:
			target_refs = _extract_target_subagent_refs(target)
			for target_ref in target_refs:
				t_kind, t_id = _agent_ref_target_id(target_ref)
				if t_id == parent_id:
					errors.append(SubAgentRefValidationError(
						field=f"{field_prefix}.agentRef",
						code="direct_cycle",
						message=(
							f"Sub-agent {target_id!r} already references this "
							"agent as a tool — direct cycle is not allowed."
						),
					))
					break

	return errors


def _extract_target_subagent_refs(target: Any) -> list[Any]:
	"""Pull a list of agent_ref-like objects from a target definition.

	The target may be a Python AgentProfile-like object, a built-in YAML
	entry mapping, or a custom-agent payload (snake_case or camelCase).
	"""
	# Dataclass / object with attribute
	attr = getattr(target, "agents_as_tools", None)
	if attr is None and isinstance(target, dict):
		attr = target.get("agents_as_tools") or target.get("agentsAsTools")
	if not isinstance(attr, list):
		return []
	# Each entry may itself have agent_ref / agentRef
	out: list[Any] = []
	for entry in attr:
		if hasattr(entry, "agent_ref"):
			out.append(entry.agent_ref)
		elif isinstance(entry, dict):
			out.append(entry.get("agent_ref") or entry.get("agentRef"))
	return out


__all__ = [
	"ALLOWED_IMAGE_MIMES",
	"MAX_IMAGE_SIZE_BYTES",
	"MAX_IMAGES_PER_MESSAGE",
	"SubAgentRefValidationError",
	"available_skill_names",
	"filter_known_skill_names",
	"known_tool_names_from_profiles",
	"validate_custom_name",
	"validate_http_mcp_servers",
	"validate_image_magic_bytes",
	"validate_prompt",
	"validate_sub_agent_tool_refs",
	"validate_temperature",
	"validate_tool_names",
	"validate_uploaded_images",
]