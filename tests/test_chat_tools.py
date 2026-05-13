"""Tests for chat.tools — schema sanity + dispatch behavior over a fake
SheetsClient."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from chat import tools
from scripts.sheets_client import MemoRow, OutcomeRow


def test_every_tool_has_unique_name_and_required_fields():
    names = [t["name"] for t in tools.TOOL_SPECS]
    assert len(names) == len(set(names)), "tool names must be unique"
    for spec in tools.TOOL_SPECS:
        assert spec.get("description"), f"{spec['name']} missing description"
        assert spec.get("input_schema", {}).get("type") == "object"


def test_dispatch_unknown_tool_returns_error_string(sheets):
    result = tools.dispatch("does_not_exist", {}, sheets)
    assert result.startswith("ERROR")


def test_read_sheet_tab_caps_at_last_n_rows(sheets):
    sheets.ensure_tab("Big", ["w", "v"])
    for i in range(20):
        sheets.append_row("Big", [f"2025-W{i:02d}", i])
    out = json.loads(tools.dispatch("read_sheet_tab", {"tab_name": "Big", "last_n_rows": 5}, sheets))
    assert out["total_rows"] == 20
    assert out["returned"] == 5
    assert out["rows"][-1]["v"] == 19


def test_read_baseline_returns_sections(sheets):
    sheets.append_row(
        "BASELINE: AdsAgent",
        ["normal_metrics", "Prospect ASC CPM $18-25", "2026-04-15", "high"],
    )
    out = json.loads(tools.dispatch("read_baseline", {"agent_name": "AdsAgent"}, sheets))
    assert out["agent"] == "AdsAgent"
    assert out["sections"][0]["section"] == "normal_metrics"


def test_read_baseline_empty_returns_human_readable_message(sheets):
    result = tools.dispatch("read_baseline", {"agent_name": "AdsAgent"}, sheets)
    assert "no baseline" in result.lower()


def test_read_recent_memos_filters_by_agent_and_window(sheets):
    now = datetime.now(timezone.utc).isoformat()
    sheets.append_memo(
        MemoRow(
            generated_at=now,
            agent="AdsAgent",
            summary="ads summary",
            diagnosis="ads diag",
            recommendations=[{"a": 1}],
            watch_list=["x"],
            data_quality="ok",
            raw_response_truncated="",
        )
    )
    sheets.append_memo(
        MemoRow(
            generated_at=now,
            agent="ProductAgent",  # different agent — should NOT appear
            summary="product summary",
            diagnosis="",
            recommendations=[],
            watch_list=[],
            data_quality="ok",
            raw_response_truncated="",
        )
    )
    out = json.loads(
        tools.dispatch("read_recent_memos", {"agent_name": "AdsAgent", "weeks_back": 4}, sheets)
    )
    assert len(out["memos"]) == 1
    assert out["memos"][0]["summary"] == "ads summary"


def test_add_lesson_writes_append_only_to_agent_knowledge(sheets):
    result = tools.dispatch(
        "add_lesson",
        {
            "agent_target": "AdsAgent",
            "category": "hard_rule",
            "lesson": "Never recommend pausing the Maria collection.",
        },
        sheets,
    )
    assert "AdsAgent" in result
    rows = sheets.read_tab("Agent Knowledge")
    assert len(rows) == 1
    assert rows[0]["agent_target"] == "AdsAgent"
    assert rows[0]["category"] == "hard_rule"
    assert rows[0]["active"] == "TRUE"
    assert "Maria" in rows[0]["lesson"]


def test_add_lesson_with_expires_at_persists_it(sheets):
    tools.dispatch(
        "add_lesson",
        {
            "agent_target": "ALL",
            "category": "preference",
            "lesson": "Skip TikTok ads through end of year.",
            "expires_at": "2026-12-31",
        },
        sheets,
    )
    rows = sheets.read_tab("Agent Knowledge")
    assert rows[0]["expires_at"] == "2026-12-31"


def test_note_for_next_run_writes_to_bot_notes(sheets):
    result = tools.dispatch(
        "note_for_next_run",
        {"note": "Wedding-season pop-up June 14-21.", "agent_target": "ALL"},
        sheets,
    )
    assert "ALL" in result
    rows = sheets.read_tab("Bot Notes")
    assert len(rows) == 1
    assert rows[0]["agent_target"] == "ALL"
    assert "Wedding" in rows[0]["note"]
    assert rows[0]["added_by"] == "bot"
    assert rows[0]["consumed_at"] == ""


def test_note_for_next_run_default_target_is_all(sheets):
    tools.dispatch("note_for_next_run", {"note": "anything"}, sheets)
    rows = sheets.read_tab("Bot Notes")
    assert rows[0]["agent_target"] == "ALL"


def test_dispatch_handles_bad_kwargs_gracefully(sheets):
    # Model passes a typo'd kwarg — we should return an ERROR string
    # rather than raise, so the model sees it and corrects.
    result = tools.dispatch("read_sheet_tab", {"tab_naem": "Big"}, sheets)
    assert result.startswith("ERROR")
