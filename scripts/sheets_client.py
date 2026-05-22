"""Google Sheets client.

Adapted from vc-drops: gspread + service account auth, retry on transient
APIError, tab bootstrap with headers. Memory + outcomes + lessons helpers
live here so all I/O is centralized.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Tab name → headers (in order). Used for first-run bootstrap.
TAB_SCHEMAS: dict[str, list[str]] = {
    "Agent Memos": [
        "generated_at",
        "agent",
        "summary",
        "diagnosis",
        "recommendations_json",
        "watch_list_json",
        "data_quality",
        "raw_response_truncated",
    ],
    "Action Plan": [
        "generated_at",
        "one_thing_this_week",
        "pace_status",
        "gap_to_close",
        "sequenced_actions_json",
        "themes_json",
        "conflicts_resolved",
        "watch_list_json",
    ],
    "Goal Tracker": [
        "week_start",
        "week_revenue",
        "ytd_revenue",
        "target_pace",
        "gap",
        "notes",
    ],
    "Agent Knowledge": [
        "added_at",
        "agent_target",
        "category",
        "lesson",
        "active",
        "expires_at",
        "source_notes",
    ],
    "Outcomes": [
        "plan_week_start",
        "action_id",
        "source_agent",
        "action_summary",
        "executed",
        "executed_when",
        "observed_outcome",
        "projected_impact_usd",
        "actual_impact_usd",
        "learning_note",
    ],
    "Runtime Log": [
        "run_at",
        "agent",
        "status",
        "duration_seconds",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "key_insight",
        "errors",
    ],
    # Bot audit trail (PR 5). Every bot-initiated write to the spreadsheet
    # appends a row here. If a write goes wrong, this is the audit log
    # Darci consults. Sheets' built-in revision history covers rollback.
    "Bot Actions": [
        "timestamp",
        "transport",
        "conversation_id",
        "tool_name",
        "tool_args_json",
        "result_summary",
        "requires_confirmation",
        "confirmed",
    ],
    # Notes the bot wants the next weekly run to see. The coordinator
    # (GoalsAgent) reads this tab and folds anything fresh into its
    # context. Append-only; weekly run marks rows as "consumed" by
    # writing to the consumed_at column.
    "Bot Notes": [
        "added_at",
        "added_by",  # "bot" or "darci"
        "agent_target",  # specific agent name or "ALL"
        "note",
        "consumed_at",
    ],
}


# Names of the 7 specialist agents that get a curated "baseline" tab.
# The baseline holds long-run wisdom (what's normal, seasonal patterns,
# hard rules) so the weekly run doesn't have to re-derive it from 50
# weeks of raw data every Monday. Refreshed monthly via Claude.ai (see
# BASELINES.md), not by the API runner.
BASELINE_AGENTS: list[str] = [
    "AdsAgent",
    "CustomerAgent",
    "ProductAgent",
    "ContentAgent",
    "FunnelAgent",
    "FinancialAgent",
    "SEOAgent",
    # The coordinator also gets a baseline tab — cross-agent themes,
    # strategic constraints, channel-mix observations that span specialists.
    "GoalsAgent",
]

BASELINE_HEADERS = ["section", "content", "last_updated", "confidence"]


def baseline_tab_name(agent_name: str) -> str:
    # "BASELINE: " prefix clusters these together in the Sheets tab list.
    return f"BASELINE: {agent_name}"


MAX_RAW_RESPONSE_CHARS = 8000

RETRYABLE_EXC = (gspread.exceptions.APIError,)


def _retry(fn, *, attempts: int = 4, base: float = 1.5):
    """Retry a callable on APIError with exponential backoff. Re-raises last."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except RETRYABLE_EXC as e:
            last = e
            if i == attempts - 1:
                break
            time.sleep(base ** i)
    assert last is not None
    raise last


@dataclass
class LessonRow:
    added_at: str
    agent_target: str
    category: str
    lesson: str
    active: bool
    expires_at: str
    source_notes: str


@dataclass
class MemoRow:
    generated_at: str
    agent: str
    summary: str
    diagnosis: str
    recommendations: list[dict]
    watch_list: list[str]
    data_quality: str
    raw_response_truncated: str


@dataclass
class OutcomeRow:
    plan_week_start: str
    action_id: str
    source_agent: str
    action_summary: str
    executed: str
    executed_when: str
    observed_outcome: str
    projected_impact_usd: float | None
    actual_impact_usd: float | None
    learning_note: str


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "yes", "1", "y"}


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        # Accept "YYYY-MM-DD" or full ISO timestamps.
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class SheetsClient:
    """Wraps a gspread.Spreadsheet with retry + memory helpers.

    Construct via `SheetsClient.from_config(config)` for production, or pass a
    spreadsheet directly for tests with a fake gspread surface.
    """

    def __init__(self, spreadsheet):
        self._ss = spreadsheet

    # ---- construction ----
    @classmethod
    def from_config(cls, config) -> "SheetsClient":
        if not config.google_service_account_json:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is required")
        if not config.google_sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is required")
        info = json.loads(config.google_service_account_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        gc = gspread.authorize(creds)
        ss = gc.open_by_key(config.google_sheet_id)
        return cls(ss)

    # ---- low-level ----
    def get_worksheet(self, title: str):
        return _retry(lambda: self._ss.worksheet(title))

    def list_tab_names(self) -> list[str]:
        """Return every tab title in the spreadsheet, in sheet order."""
        worksheets = _retry(lambda: self._ss.worksheets())
        return [ws.title for ws in worksheets]

    def ensure_tab(self, title: str, headers: list[str]) -> None:
        try:
            ws = self.get_worksheet(title)
            existing = _retry(lambda: ws.row_values(1))
            if existing != headers:
                _retry(lambda: ws.update("A1", [headers]))
        except gspread.exceptions.WorksheetNotFound:
            ws = _retry(
                lambda: self._ss.add_worksheet(
                    title=title, rows=1000, cols=max(10, len(headers))
                )
            )
            _retry(lambda: ws.update("A1", [headers]))

    def ensure_all_tabs(self) -> None:
        for title, headers in TAB_SCHEMAS.items():
            self.ensure_tab(title, headers)
        for agent_name in BASELINE_AGENTS:
            self.ensure_tab(baseline_tab_name(agent_name), BASELINE_HEADERS)

    def read_tab(self, title: str) -> list[dict]:
        ws = self.get_worksheet(title)
        return _retry(lambda: ws.get_all_records())

    def append_row(self, title: str, row: list) -> None:
        ws = self.get_worksheet(title)
        _retry(lambda: ws.append_row(row, value_input_option="USER_ENTERED"))

    # ---- baseline helpers ----
    def read_baseline_for_agent(self, agent_name: str) -> list[dict]:
        """Return baseline sections in tab order. Each section is a dict with
        keys: section, content, last_updated, confidence. Returns [] if the
        tab is missing or empty — agents handle empty baselines gracefully.
        """
        tab = baseline_tab_name(agent_name)
        try:
            rows = self.read_tab(tab)
        except gspread.exceptions.WorksheetNotFound:
            return []
        out: list[dict] = []
        for row in rows:
            section = str(row.get("section", "")).strip()
            content = str(row.get("content", "")).strip()
            if not section or not content:
                continue
            out.append(
                {
                    "section": section,
                    "content": content,
                    "last_updated": str(row.get("last_updated", "")).strip(),
                    "confidence": str(row.get("confidence", "")).strip(),
                }
            )
        return out

    # ---- memo helpers ----
    def append_memo(self, memo_row: MemoRow) -> None:
        raw = (memo_row.raw_response_truncated or "")[:MAX_RAW_RESPONSE_CHARS]
        self.append_row(
            "Agent Memos",
            [
                memo_row.generated_at,
                memo_row.agent,
                memo_row.summary,
                memo_row.diagnosis,
                json.dumps(memo_row.recommendations),
                json.dumps(memo_row.watch_list),
                memo_row.data_quality,
                raw,
            ],
        )

    def read_memos_for_agent(self, agent_name: str, weeks_back: int) -> list[MemoRow]:
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks_back)
        out: list[MemoRow] = []
        for row in self.read_tab("Agent Memos"):
            if row.get("agent") != agent_name:
                continue
            ts = _parse_iso(str(row.get("generated_at", "")))
            if ts is None or ts < cutoff:
                continue
            try:
                recs = json.loads(row.get("recommendations_json") or "[]")
            except json.JSONDecodeError:
                recs = []
            try:
                watch = json.loads(row.get("watch_list_json") or "[]")
            except json.JSONDecodeError:
                watch = []
            out.append(
                MemoRow(
                    generated_at=str(row.get("generated_at", "")),
                    agent=str(row.get("agent", "")),
                    summary=str(row.get("summary", "")),
                    diagnosis=str(row.get("diagnosis", "")),
                    recommendations=recs,
                    watch_list=watch,
                    data_quality=str(row.get("data_quality", "")),
                    raw_response_truncated=str(row.get("raw_response_truncated", "")),
                )
            )
        out.sort(key=lambda m: m.generated_at, reverse=True)
        return out

    # ---- lessons ----
    def read_lessons_for_agent(self, agent_name: str) -> list[LessonRow]:
        """Return active, non-expired lessons targeted at agent_name OR 'ALL'."""
        now = datetime.now(timezone.utc)
        out: list[LessonRow] = []
        for row in self.read_tab("Agent Knowledge"):
            target = str(row.get("agent_target", "")).strip()
            if target not in {agent_name, "ALL"}:
                continue
            if not _parse_bool(row.get("active")):
                continue
            expires_raw = str(row.get("expires_at", "")).strip()
            if expires_raw:
                expires = _parse_iso(expires_raw)
                if expires is not None and expires < now:
                    continue
            out.append(
                LessonRow(
                    added_at=str(row.get("added_at", "")),
                    agent_target=target,
                    category=str(row.get("category", "")),
                    lesson=str(row.get("lesson", "")),
                    active=True,
                    expires_at=expires_raw,
                    source_notes=str(row.get("source_notes", "")),
                )
            )
        return out

    # ---- outcomes ----
    def read_outcomes_for_agent(
        self, agent_name: str, weeks_back: int
    ) -> list[OutcomeRow]:
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks_back)
        out: list[OutcomeRow] = []
        for row in self.read_tab("Outcomes"):
            if row.get("source_agent") != agent_name:
                continue
            ts = _parse_iso(str(row.get("plan_week_start", "")))
            if ts is None or ts < cutoff:
                continue
            out.append(
                OutcomeRow(
                    plan_week_start=str(row.get("plan_week_start", "")),
                    action_id=str(row.get("action_id", "")),
                    source_agent=str(row.get("source_agent", "")),
                    action_summary=str(row.get("action_summary", "")),
                    executed=str(row.get("executed", "")),
                    executed_when=str(row.get("executed_when", "")),
                    observed_outcome=str(row.get("observed_outcome", "")),
                    projected_impact_usd=_parse_float(row.get("projected_impact_usd")),
                    actual_impact_usd=_parse_float(row.get("actual_impact_usd")),
                    learning_note=str(row.get("learning_note", "")),
                )
            )
        out.sort(key=lambda o: o.plan_week_start, reverse=True)
        return out

    # ---- action plan (coordinator output, overwritten weekly) ----
    def write_action_plan(
        self,
        *,
        generated_at: str,
        one_thing_this_week: str,
        pace_status: dict | str,
        gap_to_close: str,
        sequenced_actions: list[dict],
        themes: list[dict],
        conflicts_resolved: str,
        watch_list: list[str],
    ) -> None:
        ws = self.get_worksheet("Action Plan")
        headers = TAB_SCHEMAS["Action Plan"]
        row = [
            generated_at,
            one_thing_this_week,
            json.dumps(pace_status) if isinstance(pace_status, dict) else str(pace_status),
            gap_to_close,
            json.dumps(sequenced_actions),
            json.dumps(themes),
            conflicts_resolved,
            json.dumps(watch_list),
        ]
        # Replace contents: header row + this single row.
        _retry(lambda: ws.update("A1", [headers, row]))

    # ---- runtime log ----
    def append_runtime_log(
        self,
        *,
        run_at: str,
        agent: str,
        status: str,
        duration_seconds: float,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        key_insight: str,
        errors: str,
    ) -> None:
        self.append_row(
            "Runtime Log",
            [
                run_at,
                agent,
                status,
                round(duration_seconds, 3),
                input_tokens,
                output_tokens,
                round(cost_usd, 6),
                key_insight,
                errors,
            ],
        )
