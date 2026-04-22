"""Eval trace logger — captures per-turn data for evaluation and analysis.

Writes JSON-lines (.jsonl) trace files to a configurable directory.
Each line records one agent turn: the user input, agent output, tool calls,
available tools, token usage, and context usage.

Enable by setting EVAL_TRACE_DIR to a writable directory path.  When the
env var is unset or empty, ``EvalTraceLogger.from_env()`` returns a no-op
instance that silently discards all log calls.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EvalTraceLogger:
    """Append-only JSONL trace logger.

    Parameters
    ----------
    trace_dir:
        Directory where ``.jsonl`` trace files are written.  If ``None``,
        the logger is a no-op.
    """

    def __init__(self, trace_dir: str | Path | None = None) -> None:
        self._trace_dir: Path | None = None
        if trace_dir:
            self._trace_dir = Path(trace_dir)
            self._trace_dir.mkdir(parents=True, exist_ok=True)
            logger.info("EvalTraceLogger writing to %s", self._trace_dir)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "EvalTraceLogger":
        """Create a logger from the ``EVAL_TRACE_DIR`` environment variable.

        Returns a no-op logger when the variable is unset or empty.
        """
        trace_dir = os.environ.get("EVAL_TRACE_DIR", "").strip()
        return cls(trace_dir or None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._trace_dir is not None

    def log(self, record: dict[str, Any]) -> None:
        """Append *record* as a single JSON line to today's trace file.

        If the logger is disabled (no trace dir), this is a no-op.
        """
        if self._trace_dir is None:
            return

        now = datetime.now(timezone.utc)
        record["timestamp"] = now.isoformat()

        filename = f"trace_{now.strftime('%Y-%m-%d')}.jsonl"
        filepath = self._trace_dir / filename

        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            logger.exception("Failed to write eval trace to %s", filepath)
