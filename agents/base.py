"""Base agent for all vc-actions specialists.

Per v5 §Part 2, run() loads memory + outcomes + lessons before calling Claude,
and writes a runtime log entry whether the run succeeded or raised.
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.claude_client import ClaudeClient, parse_json_response
from scripts.config import PROMPTS_DIR, Config
from scripts.memory import (
    AgentMemory,
    load_agent_memory,
    render_memory_block,
)
from scripts.runtime_log import RuntimeEntry, write_runtime_entry
from scripts.sheets_client import MemoRow, SheetsClient


MAX_RAW_RESPONSE_CHARS = 8000


def render_baseline_block(rows: list[dict]) -> str:
    """Render the baseline tab rows into a text block for the system prompt.

    Empty baseline returns a short note rather than an empty string — agents
    rely on consistent prompt structure for the cache prefix to match.
    """
    if not rows:
        return "(no baseline yet — first run, weekly data is the only signal)"
    parts: list[str] = []
    for row in rows:
        header = f"[{row['section']}]"
        meta_bits = []
        if row.get("last_updated"):
            meta_bits.append(f"updated {row['last_updated']}")
        if row.get("confidence"):
            meta_bits.append(f"confidence={row['confidence']}")
        if meta_bits:
            header += f"  ({', '.join(meta_bits)})"
        parts.append(f"{header}\n{row['content']}")
    return "\n\n".join(parts)

JSON_OUTPUT_INSTRUCTION = """Produce a structured analysis as a JSON object matching this schema:
{
  "summary": "1-2 sentence top-line",
  "diagnosis": "2-4 sentences on what's happening this week",
  "recommendations": [
    {"priority": 1, "action": "...", "why": "...",
     "impact_dollars_per_week": 500, "confidence": "high",
     "effort": "low", "depends_on": []}
  ],
  "watch_list": ["..."],
  "data_quality": "high"
}

Return ONLY the JSON, no preamble, no code fences."""


@dataclass
class Recommendation:
    priority: int
    action: str
    why: str = ""
    impact_dollars_per_week: float = 0.0
    confidence: str = "medium"
    effort: str = "medium"
    depends_on: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Recommendation":
        return cls(
            priority=int(d.get("priority", 5)),
            action=str(d.get("action", "")),
            why=str(d.get("why", "")),
            impact_dollars_per_week=float(d.get("impact_dollars_per_week", 0) or 0),
            confidence=str(d.get("confidence", "medium")),
            effort=str(d.get("effort", "medium")),
            depends_on=list(d.get("depends_on", []) or []),
        )

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "action": self.action,
            "why": self.why,
            "impact_dollars_per_week": self.impact_dollars_per_week,
            "confidence": self.confidence,
            "effort": self.effort,
            "depends_on": list(self.depends_on),
        }


@dataclass
class AgentMemo:
    agent: str
    generated_at: str
    summary: str
    diagnosis: str
    recommendations: list[Recommendation]
    watch_list: list[str]
    data_quality: str
    raw_response: str

    def to_memo_row(self) -> MemoRow:
        return MemoRow(
            generated_at=self.generated_at,
            agent=self.agent,
            summary=self.summary,
            diagnosis=self.diagnosis,
            recommendations=[r.to_dict() for r in self.recommendations],
            watch_list=list(self.watch_list),
            data_quality=self.data_quality,
            raw_response_truncated=self.raw_response[:MAX_RAW_RESPONSE_CHARS],
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BaseAgent:
    """Every specialist agent inherits from this.

    Subclasses must set `name`, `role_prompt_file`, and override `gather_data()`.
    """

    name: str = ""
    role_prompt_file: str = ""  # relative to prompts/ dir, e.g. "ads.md"
    # Override in subclasses to route a specific agent to a cheaper model
    # (e.g. Haiku for pattern-matching agents like Content/SEO). `None` means
    # use the client's default model (set from config.anthropic_model).
    preferred_model: str | None = None

    def __init__(
        self,
        claude_client: ClaudeClient,
        sheets_client: SheetsClient,
        config: Config,
        prompts_dir: Path | None = None,
        dry_run: bool | None = None,
    ):
        if not self.name:
            raise ValueError(f"{type(self).__name__} must set `name`")
        if not self.role_prompt_file:
            raise ValueError(f"{type(self).__name__} must set `role_prompt_file`")
        self.claude = claude_client
        self.sheets = sheets_client
        self.config = config
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        # Per-instance override wins; otherwise fall back to config.
        self.dry_run = config.dry_run if dry_run is None else dry_run

    # ---- subclass hooks ----
    data_tabs: list[str] = []  # subclass override: tabs to read in gather_data()
    # Cap per-tab rows before sending to Claude. 4 weeks is enough for w/w
    # trend detection — the BASELINE tab carries the long-run wisdom
    # (what's normal, seasonal patterns), so the weekly raw data only
    # needs the recent window. Subclasses can override for denser-data
    # domains (e.g. per-ad data, daily IG posts).
    max_rows_per_tab: int = 4

    def gather_data(self) -> dict[str, Any]:
        """Default: read each tab in `data_tabs`, keeping at most
        `max_rows_per_tab` of the most recent rows. Missing tabs become
        `{"error": ...}` placeholders so a missing sheet doesn't kill the run.
        Override for agents that need custom data shaping.
        """
        if not self.data_tabs:
            raise NotImplementedError(
                f"{type(self).__name__} must either set `data_tabs` or override `gather_data()`"
            )
        out: dict[str, Any] = {}
        cap = self.max_rows_per_tab
        for tab in self.data_tabs:
            try:
                rows = self.sheets.read_tab(tab)
            except Exception as e:
                out[tab] = {"error": f"{type(e).__name__}: {e}"}
                continue
            if isinstance(rows, list) and cap and len(rows) > cap:
                # Keep the last N rows. Sheets are typically chronologically
                # ordered (oldest at top); the tail is the most recent.
                out[tab] = {
                    "_total_rows": len(rows),
                    "_kept_last": cap,
                    "rows": rows[-cap:],
                }
            else:
                out[tab] = rows
        return out

    # ---- prompt assembly ----
    def _load_text(self, filename: str) -> str:
        return (self.prompts_dir / filename).read_text()

    def get_business_context(self) -> str:
        return self._load_text("base_context.md")

    def get_role_prompt(self) -> str:
        return self._load_text(self.role_prompt_file)

    def _load_baseline(self) -> list[dict]:
        """Read the agent's BASELINE: <Agent> tab. Empty list if the tab
        is missing or has no rows yet — a fresh deploy has no baselines."""
        try:
            return self.sheets.read_baseline_for_agent(self.name)
        except Exception:
            return []

    def build_prompt(
        self,
        *,
        role_prompt: str,
        business_context: str,
        baseline: list[dict],
        memory: AgentMemory,
        data: dict[str, Any],
    ) -> tuple[list[dict], str]:
        """Returns (system_blocks, user_message).

        The system blocks are stable within a weekly run — role prompt and
        business context are identical across all 7 specialists, the
        baseline is refreshed monthly (not weekly), and the memory block
        is fixed for the duration of one agent's call. A `cache_control`
        breakpoint on the memory block tells Anthropic to cache everything
        up to that point, so the next agent in the run reads the role +
        context prefix from cache at ~10% of the normal rate.

        The user message carries this week's raw data and the output
        instruction — the volatile part that legitimately changes per run.
        """
        memory_block = render_memory_block(memory)
        baseline_block = render_baseline_block(baseline)
        data_block = json.dumps(data, indent=2, default=str)
        system_blocks: list[dict] = [
            {"type": "text", "text": role_prompt},
            {"type": "text", "text": f"BUSINESS CONTEXT:\n{business_context}"},
            {
                "type": "text",
                "text": (
                    "AGENT BASELINE (curated long-run patterns — these are "
                    "what NORMAL looks like for this business; flag deviations):\n"
                    f"{baseline_block}"
                ),
            },
            {
                "type": "text",
                "text": f"MEMORY (read carefully — lessons are HARD RULES):\n{memory_block}",
                "cache_control": {"type": "ephemeral"},
            },
        ]
        user_message = (
            f"THIS WEEK'S DATA:\n{data_block}\n\n"
            f"{JSON_OUTPUT_INSTRUCTION}\n"
        )
        return system_blocks, user_message

    # ---- response handling ----
    def parse_response(self, raw_text: str) -> AgentMemo:
        parsed = parse_json_response(raw_text)
        recs = [Recommendation.from_dict(r) for r in parsed.get("recommendations", [])]
        return AgentMemo(
            agent=self.name,
            generated_at=_now_iso(),
            summary=str(parsed.get("summary", "")),
            diagnosis=str(parsed.get("diagnosis", "")),
            recommendations=recs,
            watch_list=list(parsed.get("watch_list", []) or []),
            data_quality=str(parsed.get("data_quality", "")),
            raw_response=raw_text,
        )

    def write_memo(self, memo: AgentMemo) -> None:
        if self.dry_run:
            self._print_dry_run_memo(memo)
            return
        self.sheets.append_memo(memo.to_memo_row())

    def _print_dry_run_memo(self, memo: AgentMemo) -> None:
        bar = "=" * 72
        print(f"\n{bar}\n[DRY RUN] {memo.agent} — {memo.generated_at}\n{bar}")
        print(f"SUMMARY: {memo.summary}")
        print(f"DIAGNOSIS: {memo.diagnosis}")
        print("RECOMMENDATIONS:")
        for r in memo.recommendations:
            print(
                f"  P{r.priority} {r.action} "
                f"(${r.impact_dollars_per_week}/wk, "
                f"{r.confidence}/{r.effort})"
            )
            if r.why:
                print(f"      why: {r.why}")
        if memo.watch_list:
            print("WATCH:")
            for w in memo.watch_list:
                print(f"  - {w}")
        print(f"DATA QUALITY: {memo.data_quality}")
        print(bar)

    # ---- orchestration ----
    def run(self) -> AgentMemo:
        start = time.time()
        entry = RuntimeEntry(agent=self.name, status="ok", duration_seconds=0.0)
        try:
            role = self.get_role_prompt()
            context = self.get_business_context()
            baseline = self._load_baseline()
            memory = load_agent_memory(self.sheets, self.name)
            data = self.gather_data()
            system_blocks, user_message = self.build_prompt(
                role_prompt=role,
                business_context=context,
                baseline=baseline,
                memory=memory,
                data=data,
            )
            response = self.claude.complete(
                user_message,
                system=system_blocks,
                model=self.preferred_model,
            )
            memo = self.parse_response(response.text)
            self.write_memo(memo)

            entry.input_tokens = response.input_tokens
            entry.output_tokens = response.output_tokens
            entry.cost_usd = response.cost_usd
            entry.key_insight = memo.summary[:280]
            return memo
        except Exception as e:
            entry.status = "error"
            entry.errors = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"
            raise
        finally:
            entry.duration_seconds = time.time() - start
            if self.dry_run:
                print(
                    f"[DRY RUN] {self.name} runtime: "
                    f"{entry.duration_seconds:.2f}s, "
                    f"in={entry.input_tokens}, out={entry.output_tokens}, "
                    f"cost=${entry.cost_usd:.4f}, status={entry.status}"
                )
            else:
                try:
                    write_runtime_entry(self.sheets, entry)
                except Exception:
                    # Never let logging mask the real failure.
                    pass
