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

    def __init__(
        self,
        claude_client: ClaudeClient,
        sheets_client: SheetsClient,
        config: Config,
        prompts_dir: Path | None = None,
    ):
        if not self.name:
            raise ValueError(f"{type(self).__name__} must set `name`")
        if not self.role_prompt_file:
            raise ValueError(f"{type(self).__name__} must set `role_prompt_file`")
        self.claude = claude_client
        self.sheets = sheets_client
        self.config = config
        self.prompts_dir = prompts_dir or PROMPTS_DIR

    # ---- subclass hooks ----
    def gather_data(self) -> dict[str, Any]:
        raise NotImplementedError

    # ---- prompt assembly ----
    def _load_text(self, filename: str) -> str:
        return (self.prompts_dir / filename).read_text()

    def get_business_context(self) -> str:
        return self._load_text("base_context.md")

    def get_role_prompt(self) -> str:
        return self._load_text(self.role_prompt_file)

    def build_prompt(
        self,
        *,
        role_prompt: str,
        business_context: str,
        memory: AgentMemory,
        data: dict[str, Any],
    ) -> str:
        memory_block = render_memory_block(memory)
        data_block = json.dumps(data, indent=2, default=str)
        return (
            f"{role_prompt}\n\n"
            f"BUSINESS CONTEXT:\n{business_context}\n\n"
            f"MEMORY (read carefully — lessons are HARD RULES):\n{memory_block}\n\n"
            f"THIS WEEK'S DATA:\n{data_block}\n\n"
            f"{JSON_OUTPUT_INSTRUCTION}\n"
        )

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
        self.sheets.append_memo(memo.to_memo_row())

    # ---- orchestration ----
    def run(self) -> AgentMemo:
        start = time.time()
        entry = RuntimeEntry(agent=self.name, status="ok", duration_seconds=0.0)
        try:
            role = self.get_role_prompt()
            context = self.get_business_context()
            memory = load_agent_memory(self.sheets, self.name)
            data = self.gather_data()
            prompt = self.build_prompt(
                role_prompt=role,
                business_context=context,
                memory=memory,
                data=data,
            )
            response = self.claude.complete(prompt)
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
            try:
                write_runtime_entry(self.sheets, entry)
            except Exception:
                # Never let logging mask the real failure.
                pass
