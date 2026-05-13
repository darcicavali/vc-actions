"""Tool definitions and dispatchers for the chat brain.

Two halves:

1. `TOOL_SPECS` — the JSON schemas Claude sees. These are stable across
   the conversation, which is critical for prompt caching: any change to
   this list invalidates the cached system + tools prefix.

2. `dispatch(tool_name, tool_input, sheets)` — runs the tool and returns
   the string the model reads as the tool result. Pure function over
   `sheets`; transports inject their own SheetsClient.

Read tools never confirm. Write tools are gated via `chat.guardrails`.

We deliberately START SMALL — 5 read tools + 2 append-only write tools.
The bot can do meaningful work with this surface; we'll add more (Shopify
queries, GA4 reports, code execution charts) in follow-up PRs once Darci
shows us where the friction is.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


# Tool schemas surfaced to Claude. Keep descriptions instructive — the
# model uses them to decide WHEN to call. Match field names to what the
# Sheets layer expects so there's no translation surface in dispatch().

TOOL_SPECS: list[dict] = [
    {
        "name": "read_sheet_tab",
        "description": (
            "Read rows from any tab in the Vanessa Cavali spreadsheet. "
            "Use this when the user asks about historical data, current "
            "metrics, or anything the weekly run produced. Returns the "
            "most recent N rows (default 12) as JSON. Tab names are "
            "case-sensitive (e.g. 'Meta Ads Summary', 'Agent Memos', "
            "'Action Plan', 'Weekly Summary'). Common tabs: Meta Ads "
            "Summary, IG Posts, Customer Rankings, Agent Memos, "
            "Outcomes, Action Plan, Goal Tracker."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tab_name": {
                    "type": "string",
                    "description": "Exact Sheets tab name.",
                },
                "last_n_rows": {
                    "type": "integer",
                    "description": "Most recent N rows to return. Default 12.",
                    "default": 12,
                },
            },
            "required": ["tab_name"],
        },
    },
    {
        "name": "read_baseline",
        "description": (
            "Read the curated baseline doc for one specialist agent. "
            "Baselines capture what NORMAL looks like (typical metric "
            "ranges, seasonal patterns, attribution caveats, hard rules). "
            "Use this when the user asks about an agent's reasoning or "
            "what the agent considers normal. Agent names: AdsAgent, "
            "CustomerAgent, ProductAgent, ContentAgent, FunnelAgent, "
            "FinancialAgent, SEOAgent, GoalsAgent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string"},
            },
            "required": ["agent_name"],
        },
    },
    {
        "name": "read_recent_memos",
        "description": (
            "Read the most recent weekly memos from one specialist agent. "
            "Each memo contains diagnosis, recommendations, and confidence. "
            "Use when the user asks 'what did AdsAgent say last week' or "
            "wants to compare recent recommendations. weeks_back default 4."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string"},
                "weeks_back": {"type": "integer", "default": 4},
            },
            "required": ["agent_name"],
        },
    },
    {
        "name": "read_action_plan",
        "description": (
            "Read THIS week's coordinator-produced action plan — the "
            "single 'one thing this week', sequenced actions, and "
            "watch list. Use this when the user asks 'what's the plan' "
            "or 'what should I do this week'."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_outcomes",
        "description": (
            "Read past recommendation outcomes — what was tried, what "
            "happened, projected vs actual impact. Use when calibrating "
            "future projections, or when the user asks 'did X work last "
            "time'. Returns most recent first. weeks_back default 12."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": (
                        "Optional: filter to one agent's recommendations. "
                        "Omit for all agents."
                    ),
                },
                "weeks_back": {"type": "integer", "default": 12},
            },
        },
    },
    {
        "name": "add_lesson",
        "description": (
            "Append a hard rule / lesson the agents should follow on "
            "future weekly runs. Use when the user says something like "
            "'never recommend X', 'always do Y', or 'remember Z'. "
            "Append-only — does not overwrite existing lessons."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_target": {
                    "type": "string",
                    "description": (
                        "Specific agent name (e.g. 'AdsAgent') or 'ALL' "
                        "to target every agent."
                    ),
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Short tag: 'hard_rule', 'attribution', 'caveat', "
                        "'preference', etc."
                    ),
                },
                "lesson": {
                    "type": "string",
                    "description": "The rule itself, in one or two sentences.",
                },
                "expires_at": {
                    "type": "string",
                    "description": (
                        "Optional ISO date (YYYY-MM-DD) after which the "
                        "lesson is ignored. Omit for permanent rules."
                    ),
                },
            },
            "required": ["agent_target", "category", "lesson"],
        },
    },
    {
        "name": "note_for_next_run",
        "description": (
            "Append a note the next weekly run will fold into the "
            "GoalsAgent context. Use when Darci shares context the bot "
            "should pass forward — 'we're running a sale next week', "
            "'inventory delayed by 2 weeks', etc. Append-only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_target": {
                    "type": "string",
                    "description": "Specific agent or 'ALL'. Default 'ALL'.",
                    "default": "ALL",
                },
                "note": {"type": "string"},
            },
            "required": ["note"],
        },
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---- dispatch ----------------------------------------------------------


def dispatch(tool_name: str, tool_input: dict, sheets) -> str:
    """Execute one tool call and return the string the model will read.

    All return values are JSON-serializable strings — the model parses
    them back. Errors return a short string with `is_error` semantics
    handled by the brain (which sets `is_error: True` on the
    tool_result block).
    """
    try:
        if tool_name == "read_sheet_tab":
            return _read_sheet_tab(sheets, **tool_input)
        if tool_name == "read_baseline":
            return _read_baseline(sheets, **tool_input)
        if tool_name == "read_recent_memos":
            return _read_recent_memos(sheets, **tool_input)
        if tool_name == "read_action_plan":
            return _read_action_plan(sheets)
        if tool_name == "read_outcomes":
            return _read_outcomes(sheets, **tool_input)
        if tool_name == "add_lesson":
            return _add_lesson(sheets, **tool_input)
        if tool_name == "note_for_next_run":
            return _note_for_next_run(sheets, **tool_input)
    except TypeError as e:
        # Most often: model passed an unexpected kwarg. Return a clear
        # error so it can correct on the next turn.
        return f"ERROR: bad arguments for {tool_name}: {e}"
    except Exception as e:  # noqa: BLE001 — surface any read error to model
        return f"ERROR: {tool_name} failed: {e}"
    return f"ERROR: unknown tool '{tool_name}'"


def _read_sheet_tab(sheets, *, tab_name: str, last_n_rows: int = 12) -> str:
    rows = sheets.read_tab(tab_name)
    total = len(rows)
    kept = rows[-last_n_rows:] if last_n_rows and total > last_n_rows else rows
    return json.dumps(
        {"tab": tab_name, "total_rows": total, "returned": len(kept), "rows": kept},
        default=str,
        indent=2,
    )


def _read_baseline(sheets, *, agent_name: str) -> str:
    rows = sheets.read_baseline_for_agent(agent_name)
    if not rows:
        return f"(no baseline yet for {agent_name})"
    return json.dumps({"agent": agent_name, "sections": rows}, default=str, indent=2)


def _read_recent_memos(sheets, *, agent_name: str, weeks_back: int = 4) -> str:
    memos = sheets.read_memos_for_agent(agent_name, weeks_back=weeks_back)
    out = [
        {
            "generated_at": m.generated_at,
            "summary": m.summary,
            "diagnosis": m.diagnosis,
            "recommendations": m.recommendations,
            "watch_list": m.watch_list,
            "data_quality": m.data_quality,
        }
        for m in memos
    ]
    return json.dumps({"agent": agent_name, "memos": out}, default=str, indent=2)


def _read_action_plan(sheets) -> str:
    rows = sheets.read_tab("Action Plan")
    if not rows:
        return "(no action plan yet — has the weekly run produced one?)"
    # The Action Plan tab is overwritten weekly; the latest is row 0.
    latest = rows[0] if isinstance(rows, list) else rows
    return json.dumps({"action_plan": latest}, default=str, indent=2)


def _read_outcomes(sheets, *, agent_name: str | None = None, weeks_back: int = 12) -> str:
    if agent_name:
        outcomes = sheets.read_outcomes_for_agent(agent_name, weeks_back=weeks_back)
        out = [
            {
                "plan_week_start": o.plan_week_start,
                "action_summary": o.action_summary,
                "executed": o.executed,
                "observed_outcome": o.observed_outcome,
                "projected_impact_usd": o.projected_impact_usd,
                "actual_impact_usd": o.actual_impact_usd,
                "learning_note": o.learning_note,
            }
            for o in outcomes
        ]
        return json.dumps({"agent": agent_name, "outcomes": out}, default=str, indent=2)
    # All agents: just dump the recent rows from the tab.
    rows = sheets.read_tab("Outcomes")
    return json.dumps(
        {"outcomes": rows[-50:] if len(rows) > 50 else rows},
        default=str,
        indent=2,
    )


def _add_lesson(
    sheets,
    *,
    agent_target: str,
    category: str,
    lesson: str,
    expires_at: str = "",
) -> str:
    sheets.append_row(
        "Agent Knowledge",
        [
            _now_iso(),
            agent_target,
            category,
            lesson,
            "TRUE",
            expires_at,
            "added via chat bot",
        ],
    )
    return f"Lesson added for {agent_target} (category={category})."


def _note_for_next_run(sheets, *, note: str, agent_target: str = "ALL") -> str:
    sheets.append_row(
        "Bot Notes",
        [_now_iso(), "bot", agent_target, note, ""],
    )
    return f"Note recorded for {agent_target}, next weekly run will see it."
