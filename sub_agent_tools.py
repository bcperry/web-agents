"""Sub-agent tool helpers — derivation rules and tool-name disambiguation.

Pure functions only. No agent_framework imports. The runtime wiring lives in
``agent_factory.py``; this module exists so the slugify / disambiguate logic
is small, dependency-free, and trivially unit-testable.

Spec: specs/008-agents-as-tools/contracts/agent-schema.md "Derivation Rules"
"""

from __future__ import annotations

import re
from typing import Iterable

# Maximum length permitted by most LLM tool-call function-name slots.
_TOOL_NAME_MAX_LEN = 64

# Maximum length we expose for a derived tool description.
_TOOL_DESC_MAX_LEN = 500

# Run of any character that is NOT [a-zA-Z0-9].
_NON_WORD_RUN = re.compile(r"[^a-zA-Z0-9]+")


def _slugify(name: str) -> str:
    """Lowercase, replace non-word runs with `_`, strip leading/trailing `_`."""
    if not name:
        return ""
    slug = _NON_WORD_RUN.sub("_", name.strip().lower()).strip("_")
    if slug and slug[0].isdigit():
        slug = "a_" + slug
    return slug[:_TOOL_NAME_MAX_LEN]


def derive_sub_agent_tool_surface(
    target_agent_name: str,
    target_agent_description: str,
    agent_id_fallback: str,
) -> tuple[str, str, str]:
    """Return ``(tool_name, tool_description, arg_description)`` for a sub-agent ref.

    Rules (normative, see contracts/agent-schema.md):

    - ``tool_name`` = slugify(target_agent_name); on empty, fall back to
      slugify(agent_id_fallback); on still-empty, fall back to the literal
      string ``"sub_agent"``.
    - ``tool_description`` = target_agent_description, truncated to 500 chars;
      on empty, fall back to ``"Delegate to the {target_agent_name} agent."``
      (or the slugified id if the name is also empty).
    - ``arg_description`` = ``"Request for the {tool_name} agent."``
    """
    tool_name = _slugify(target_agent_name) or _slugify(agent_id_fallback) or "sub_agent"

    description = (target_agent_description or "").strip()
    if description:
        if len(description) > _TOOL_DESC_MAX_LEN:
            description = description[:_TOOL_DESC_MAX_LEN]
    else:
        display = (target_agent_name or "").strip() or agent_id_fallback or tool_name
        description = f"Delegate to the {display} agent."

    arg_description = f"Request for the {tool_name} agent."
    return tool_name, description, arg_description


def disambiguate_tool_names(names: Iterable[str], *, reserved_names: Iterable[str] = ()) -> list[str]:
    """Return ``names`` with duplicates suffixed ``_2``, ``_3``, … in order.

    The first occurrence of each name keeps its original spelling; subsequent
    occurrences are renamed with the lowest unused numeric suffix that does
    not itself collide with an earlier (or already-renamed) name.

    >>> disambiguate_tool_names(["a", "b", "a", "a"])
    ['a', 'b', 'a_2', 'a_3']
    >>> disambiguate_tool_names(["a", "a_2", "a"])
    ['a', 'a_2', 'a_3']
    """
    seen: set[str] = set(reserved_names)
    out: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
            continue
        suffix = 2
        while True:
            ending = f"_{suffix}"
            candidate = f"{name[:_TOOL_NAME_MAX_LEN - len(ending)]}{ending}"
            if candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
                break
            suffix += 1
    return out


__all__ = [
    "derive_sub_agent_tool_surface",
    "disambiguate_tool_names",
]
