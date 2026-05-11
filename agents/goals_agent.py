"""GoalsAgent — strategic coordinator (fractional COO).

Reads all this-week specialist memos + Goal Tracker + Weekly Summary, then
asks Claude to produce ONE unified action plan. Writes the structured plan
to the `Action Plan` tab (overwritten weekly) and also appends a memo to
`Agent Memos` so its own history is available to the memory layer.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from agents.base import (
    JSON_OUTPUT_INSTRUCTION,
    AgentMemo,
    BaseAgent,
    Recommendation,
    _now_iso,
)
from scripts.claude_client import parse_json_response


COORDINATOR_OUTPUT_INSTRUCTION = """Produce a structured plan as a JSON object with this exact schema:
{
  "summary": "2-sentence top-line for the week",
  "one_thing_this_week": "single highest-leverage move",
  "pace_status": {
    "ytd_revenue": 0,
    "target_ytd": 0,
    "gap": 0,
    "pace_signal": "behind|on_pace|ahead",
    "weeks_remaining": 0,
    "needed_per_week": 0
  },
  "themes": [
    {"theme": "...", "supporting_agents": ["AdsAgent", "ProductAgent"], "implication": "..."}
  ],
  "sequenced_actions": [
    {"priority": 1, "day": "Monday", "action": "...", "agent_source": "AdsAgent",
     "effort": "low", "impact_dollars_per_week": 50, "depends_on": []}
  ],
  "conflicts_resolved": [
    {"conflict": "...", "resolution": "..."}
  ],
  "watch_list": ["things to revisit next week"],
  "summary_email_body": "human-readable text for Darci's email"
}

Return ONLY the JSON, no preamble, no code fences."""


SPECIALIST_NAMES = (
    "AdsAgent",
    "CustomerAgent",
    "ProductAgent",
    "ContentAgent",
    "FunnelAgent",
    "FinancialAgent",
    "SEOAgent",
)


@dataclass
class ActionPlan:
    generated_at: str
    summary: str
    one_thing_this_week: str
    pace_status: dict
    themes: list[dict]
    sequenced_actions: list[dict]
    conflicts_resolved: list[dict] | str
    watch_list: list[str]
    summary_email_body: str
    raw_response: str = ""

    @property
    def gap_to_close(self) -> str:
        gap = self.pace_status.get("gap") if isinstance(self.pace_status, dict) else None
        return str(gap) if gap is not None else ""

    @property
    def conflicts_resolved_str(self) -> str:
        if isinstance(self.conflicts_resolved, str):
            return self.conflicts_resolved
        return json.dumps(self.conflicts_resolved)


class GoalsAgent(BaseAgent):
    """Coordinator. Reads all specialist memos for the current week and
    synthesizes them into one plan."""

    name = "GoalsAgent"
    role_prompt_file = "coordinator.md"

    # Memos are read freshly within the last N hours of this run.
    SAME_RUN_WINDOW_HOURS = 6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_plan: ActionPlan | None = None

    # ---- data ----
    def gather_data(self) -> dict[str, Any]:
        """Pull this-week specialist memos + Goal Tracker + Weekly Summary."""
        memos_by_agent: dict[str, dict] = {}
        try:
            all_memos = self.sheets.read_tab("Agent Memos")
        except Exception:
            all_memos = []

        cutoff = datetime.now(timezone.utc).timestamp() - (
            self.SAME_RUN_WINDOW_HOURS * 3600
        )
        for row in all_memos:
            agent = str(row.get("agent", ""))
            if agent not in SPECIALIST_NAMES:
                continue
            ts_str = str(row.get("generated_at", ""))
            try:
                # Accept ISO with or without timezone.
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                ts_epoch = ts.timestamp()
            except ValueError:
                continue
            existing = memos_by_agent.get(agent)
            if existing is None or ts_epoch > existing["_ts"]:
                memos_by_agent[agent] = {**row, "_ts": ts_epoch}

        # Only keep memos from THIS run (within the window).
        this_week_memos = []
        for agent, row in memos_by_agent.items():
            if row["_ts"] < cutoff:
                continue
            cleaned = {k: v for k, v in row.items() if k != "_ts"}
            # Decode JSON payloads so the model sees structured data.
            for json_field in ("recommendations_json", "watch_list_json"):
                if json_field in cleaned:
                    try:
                        cleaned[json_field] = json.loads(cleaned[json_field] or "[]")
                    except (json.JSONDecodeError, TypeError):
                        cleaned[json_field] = []
            this_week_memos.append(cleaned)

        try:
            goal_tracker = self.sheets.read_tab("Goal Tracker")
        except Exception as e:
            goal_tracker = {"error": f"{type(e).__name__}: {e}"}

        try:
            weekly_summary = self.sheets.read_tab("Weekly Summary")
        except Exception as e:
            weekly_summary = {"error": f"{type(e).__name__}: {e}"}

        return {
            "specialist_memos_this_week": this_week_memos,
            "memo_count": len(this_week_memos),
            "expected_specialists": list(SPECIALIST_NAMES),
            "missing_specialists": [
                a for a in SPECIALIST_NAMES if a not in memos_by_agent
            ],
            "Goal Tracker": goal_tracker,
            "Weekly Summary": weekly_summary,
        }

    # ---- prompt assembly: swap the JSON instruction for the coordinator schema ----
    def build_prompt(self, *, role_prompt, business_context, memory, data):
        memory_block = ""
        from scripts.memory import render_memory_block

        memory_block = render_memory_block(memory)
        data_block = json.dumps(data, indent=2, default=str)
        return (
            f"{role_prompt}\n\n"
            f"BUSINESS CONTEXT:\n{business_context}\n\n"
            f"MEMORY (read carefully — lessons are HARD RULES):\n{memory_block}\n\n"
            f"THIS WEEK'S DATA:\n{data_block}\n\n"
            f"{COORDINATOR_OUTPUT_INSTRUCTION}\n"
        )

    # ---- response parsing: produce both an AgentMemo and an ActionPlan ----
    def parse_response(self, raw_text: str) -> AgentMemo:
        parsed = parse_json_response(raw_text)

        sequenced = list(parsed.get("sequenced_actions", []) or [])
        themes = list(parsed.get("themes", []) or [])
        pace = parsed.get("pace_status", {}) or {}
        if not isinstance(pace, dict):
            pace = {"raw": pace}
        watch = list(parsed.get("watch_list", []) or [])
        conflicts = parsed.get("conflicts_resolved", []) or []

        plan = ActionPlan(
            generated_at=_now_iso(),
            summary=str(parsed.get("summary", "")),
            one_thing_this_week=str(parsed.get("one_thing_this_week", "")),
            pace_status=pace,
            themes=themes,
            sequenced_actions=sequenced,
            conflicts_resolved=conflicts,
            watch_list=watch,
            summary_email_body=str(parsed.get("summary_email_body", "")),
            raw_response=raw_text,
        )
        self._last_plan = plan

        # Map sequenced actions onto Recommendation for the Agent Memos row.
        recs = [
            Recommendation(
                priority=int(a.get("priority", 5)),
                action=str(a.get("action", "")),
                why=f"[{a.get('agent_source', '?')}] on {a.get('day', '?')}",
                impact_dollars_per_week=float(a.get("impact_dollars_per_week", 0) or 0),
                confidence="medium",
                effort=str(a.get("effort", "medium")),
                depends_on=list(a.get("depends_on", []) or []),
            )
            for a in sequenced
        ]

        diagnosis_parts = [
            f"One thing: {plan.one_thing_this_week}",
            "Themes: " + "; ".join(t.get("theme", "") for t in themes if t),
        ]
        return AgentMemo(
            agent=self.name,
            generated_at=plan.generated_at,
            summary=plan.summary,
            diagnosis=" | ".join(p for p in diagnosis_parts if p),
            recommendations=recs,
            watch_list=watch,
            data_quality=str(parsed.get("data_quality", "medium")),
            raw_response=raw_text,
        )

    # ---- write: memo to Agent Memos + structured plan to Action Plan ----
    def write_memo(self, memo: AgentMemo) -> None:
        if self.dry_run:
            self._print_dry_run_memo(memo)
            if self._last_plan is not None:
                print(f"[DRY RUN] one_thing_this_week: {self._last_plan.one_thing_this_week}")
                print(f"[DRY RUN] sequenced_actions: {len(self._last_plan.sequenced_actions)}")
            return

        super().write_memo(memo)
        if self._last_plan is None:
            return
        plan = self._last_plan
        self.sheets.write_action_plan(
            generated_at=plan.generated_at,
            one_thing_this_week=plan.one_thing_this_week,
            pace_status=plan.pace_status,
            gap_to_close=plan.gap_to_close,
            sequenced_actions=plan.sequenced_actions,
            themes=plan.themes,
            conflicts_resolved=plan.conflicts_resolved_str,
            watch_list=plan.watch_list,
        )

    # ---- public accessor for runner.py to read the action plan + email body ----
    @property
    def last_plan(self) -> ActionPlan | None:
        return self._last_plan
