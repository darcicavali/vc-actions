"""Memory loading + prompt-context formatting.

Pulls the three memory layers an agent needs (active lessons, own memos,
own outcomes) and produces deterministic, model-friendly text blocks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from scripts.sheets_client import LessonRow, MemoRow, OutcomeRow, SheetsClient


DEFAULT_WEEKS = 4


@dataclass
class AgentMemory:
    lessons: list[LessonRow]
    past_memos: list[MemoRow]
    past_outcomes: list[OutcomeRow]

    @property
    def is_empty(self) -> bool:
        return not self.lessons and not self.past_memos and not self.past_outcomes


def load_agent_memory(
    sheets: SheetsClient, agent_name: str, weeks: int = DEFAULT_WEEKS
) -> AgentMemory:
    """Best-effort: missing tabs / parse errors degrade to empty lists."""
    try:
        lessons = sheets.read_lessons_for_agent(agent_name)
    except Exception:
        lessons = []
    try:
        memos = sheets.read_memos_for_agent(agent_name, weeks)
    except Exception:
        memos = []
    try:
        outcomes = sheets.read_outcomes_for_agent(agent_name, weeks)
    except Exception:
        outcomes = []
    return AgentMemory(lessons=lessons, past_memos=memos, past_outcomes=outcomes)


def format_lessons(lessons: list[LessonRow]) -> str:
    if not lessons:
        return "(no active lessons)"
    parts = []
    for lr in lessons:
        scope = "ALL" if lr.agent_target == "ALL" else "you"
        cat = f"[{lr.category}]" if lr.category else ""
        expiry = f" (expires {lr.expires_at})" if lr.expires_at else ""
        parts.append(f"- ({scope}) {cat} {lr.lesson}{expiry}")
    return "\n".join(parts)


def format_past_memos(memos: list[MemoRow]) -> str:
    if not memos:
        return "(no prior memos)"
    parts = []
    for m in memos:
        rec_lines = []
        for r in m.recommendations:
            rec_lines.append(
                f"    - P{r.get('priority', '?')} {r.get('action', '')} "
                f"(impact ${r.get('impact_dollars_per_week', '?')}/wk, "
                f"conf={r.get('confidence', '?')})"
            )
        recs = "\n".join(rec_lines) or "    (none)"
        parts.append(
            f"- {m.generated_at}: {m.summary}\n"
            f"  diagnosis: {m.diagnosis}\n"
            f"  recommendations:\n{recs}"
        )
    return "\n".join(parts)


def format_outcomes(outcomes: list[OutcomeRow]) -> str:
    if not outcomes:
        return "(no recorded outcomes)"
    parts = []
    for o in outcomes:
        proj = o.projected_impact_usd if o.projected_impact_usd is not None else "?"
        act = o.actual_impact_usd if o.actual_impact_usd is not None else "?"
        parts.append(
            f"- week {o.plan_week_start} action={o.action_summary}\n"
            f"  executed={o.executed}, projected=${proj}, actual=${act}\n"
            f"  observed: {o.observed_outcome}\n"
            f"  note: {o.learning_note}"
        )
    return "\n".join(parts)


def render_memory_block(memory: AgentMemory) -> str:
    return (
        "ACTIVE LESSONS (HARD RULES):\n"
        f"{format_lessons(memory.lessons)}\n\n"
        "YOUR MEMOS FROM THE LAST 4 WEEKS:\n"
        f"{format_past_memos(memory.past_memos)}\n\n"
        "OUTCOMES OF YOUR PAST RECOMMENDATIONS:\n"
        f"{format_outcomes(memory.past_outcomes)}"
    )
