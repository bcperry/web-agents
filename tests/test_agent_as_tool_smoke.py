"""Smoke test: confirm the agent_framework Agent class exposes .as_tool().

This validates Research Decision R2 in specs/008-agents-as-tools/research.md —
that the RuntimeAgent produced by ``OpenAIChatClient().as_agent(...)`` is the
same ``agent_framework.Agent`` class used by the upstream sample, and
therefore exposes the ``as_tool()`` method.

The test is a pure import/attribute check; it does NOT call the Azure
OpenAI service.
"""

from __future__ import annotations

import pytest


def test_agent_class_exposes_as_tool() -> None:
    """The Agent class must expose ``as_tool`` (used to wrap sub-agents)."""
    agent_module = pytest.importorskip("agent_framework")
    agent_cls = getattr(agent_module, "Agent", None)
    assert agent_cls is not None, "agent_framework.Agent must be importable"
    assert callable(getattr(agent_cls, "as_tool", None)), (
        "agent_framework.Agent.as_tool must exist; without it the "
        "Agents-as-Tools feature cannot wrap sub-agents."
    )


def test_runtime_agent_alias_matches_agent_class() -> None:
    """The RuntimeAgent alias used by agent_factory must be agent_framework.Agent.

    agent_factory imports ``from agent_framework import Agent as RuntimeAgent``,
    so the alias and the canonical class must be the same object — ensuring
    ``as_tool`` is available on the runtime agents we build.
    """
    pytest.importorskip("agent_framework")
    from agent_framework import Agent  # type: ignore[import-not-found]

    from agent_factory import RuntimeAgent  # noqa: PLC0415  (deferred import)

    assert RuntimeAgent is Agent
