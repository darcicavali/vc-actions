"""Per-agent runtime metric capture.

Used by BaseAgent.run() to write one row to the Runtime Log tab per
invocation, whether the agent succeeded or raised.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from scripts.sheets_client import SheetsClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RuntimeEntry:
    agent: str
    status: str  # "ok" | "error"
    duration_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    key_insight: str = ""
    errors: str = ""
    run_at: str = field(default_factory=_now_iso)


def write_runtime_entry(sheets: SheetsClient, entry: RuntimeEntry) -> None:
    sheets.append_runtime_log(
        run_at=entry.run_at,
        agent=entry.agent,
        status=entry.status,
        duration_seconds=entry.duration_seconds,
        input_tokens=entry.input_tokens,
        output_tokens=entry.output_tokens,
        cost_usd=entry.cost_usd,
        key_insight=entry.key_insight,
        errors=entry.errors,
    )
