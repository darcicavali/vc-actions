import json
from datetime import datetime, timedelta, timezone

from scripts.sheets_client import (
    TAB_SCHEMAS,
    MemoRow,
    SheetsClient,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def test_ensure_all_tabs_creates_every_tab(fake_spreadsheet):
    client = SheetsClient(fake_spreadsheet)
    client.ensure_all_tabs()
    for tab, headers in TAB_SCHEMAS.items():
        ws = fake_spreadsheet.worksheet(tab)
        assert ws.row_values(1) == headers


def test_ensure_tab_fixes_drifted_headers(fake_spreadsheet):
    fake_spreadsheet.add_worksheet("Agent Memos", rows=10, cols=10)
    ws = fake_spreadsheet.worksheet("Agent Memos")
    ws.update("A1", [["wrong", "headers"]])
    client = SheetsClient(fake_spreadsheet)
    client.ensure_tab("Agent Memos", TAB_SCHEMAS["Agent Memos"])
    assert ws.row_values(1) == TAB_SCHEMAS["Agent Memos"]


def test_append_and_read_memo(sheets):
    sheets.append_memo(
        MemoRow(
            generated_at=_iso(datetime.now(timezone.utc)),
            agent="AdsAgent",
            summary="ok",
            diagnosis="dx",
            recommendations=[{"priority": 1, "action": "scale", "impact_dollars_per_week": 40}],
            watch_list=["freq creep"],
            data_quality="high",
            raw_response_truncated="raw",
        )
    )
    memos = sheets.read_memos_for_agent("AdsAgent", weeks_back=4)
    assert len(memos) == 1
    assert memos[0].summary == "ok"
    assert memos[0].recommendations[0]["action"] == "scale"


def test_read_memos_filters_old_and_other_agents(sheets):
    recent = _iso(datetime.now(timezone.utc) - timedelta(days=2))
    old = _iso(datetime.now(timezone.utc) - timedelta(weeks=10))
    sheets.append_row(
        "Agent Memos",
        [recent, "AdsAgent", "fresh", "dx", "[]", "[]", "high", "raw"],
    )
    sheets.append_row(
        "Agent Memos",
        [old, "AdsAgent", "stale", "dx", "[]", "[]", "high", "raw"],
    )
    sheets.append_row(
        "Agent Memos",
        [recent, "CustomerAgent", "other", "dx", "[]", "[]", "high", "raw"],
    )
    memos = sheets.read_memos_for_agent("AdsAgent", weeks_back=4)
    assert [m.summary for m in memos] == ["fresh"]


def test_read_lessons_filters_inactive_and_expired_and_targets_correctly(sheets):
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=1)).date().isoformat()
    future = (now + timedelta(days=30)).date().isoformat()
    # active, AdsAgent
    sheets.append_row(
        "Agent Knowledge",
        [now.date().isoformat(), "AdsAgent", "vendor", "no Maria reorder", "TRUE", "", ""],
    )
    # active, ALL
    sheets.append_row(
        "Agent Knowledge",
        [now.date().isoformat(), "ALL", "strategy", "no TikTok", "TRUE", "", ""],
    )
    # inactive
    sheets.append_row(
        "Agent Knowledge",
        [now.date().isoformat(), "AdsAgent", "x", "deactivated", "FALSE", "", ""],
    )
    # expired
    sheets.append_row(
        "Agent Knowledge",
        [now.date().isoformat(), "AdsAgent", "x", "expired rule", "TRUE", past, ""],
    )
    # other agent
    sheets.append_row(
        "Agent Knowledge",
        [now.date().isoformat(), "CustomerAgent", "x", "B2B win-back", "TRUE", "", ""],
    )
    # future-expiring counts as active
    sheets.append_row(
        "Agent Knowledge",
        [now.date().isoformat(), "ALL", "financial", "preserve cash", "TRUE", future, ""],
    )

    lessons = sheets.read_lessons_for_agent("AdsAgent")
    texts = {l.lesson for l in lessons}
    assert texts == {"no Maria reorder", "no TikTok", "preserve cash"}


def test_read_outcomes_filters_by_agent_and_window(sheets):
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    old = (datetime.now(timezone.utc) - timedelta(weeks=10)).date().isoformat()
    sheets.append_row(
        "Outcomes",
        [recent, "a1", "AdsAgent", "scale Prospect", "Y", recent, "no lift", 200, 50, "over-projected"],
    )
    sheets.append_row(
        "Outcomes",
        [old, "a0", "AdsAgent", "old action", "Y", old, "ok", 100, 100, ""],
    )
    sheets.append_row(
        "Outcomes",
        [recent, "p1", "ProductAgent", "reorder", "Y", recent, "ok", 1000, 1100, ""],
    )
    outcomes = sheets.read_outcomes_for_agent("AdsAgent", weeks_back=4)
    assert len(outcomes) == 1
    assert outcomes[0].action_id == "a1"
    assert outcomes[0].projected_impact_usd == 200.0
    assert outcomes[0].actual_impact_usd == 50.0


def test_append_runtime_log(sheets, fake_spreadsheet):
    sheets.append_runtime_log(
        run_at="2026-05-11T08:00:00+00:00",
        agent="AdsAgent",
        status="ok",
        duration_seconds=12.345,
        input_tokens=1000,
        output_tokens=200,
        cost_usd=0.0123456,
        key_insight="cold healthy",
        errors="",
    )
    ws = fake_spreadsheet.worksheet("Runtime Log")
    rows = ws.get_all_records()
    assert len(rows) == 1
    assert rows[0]["agent"] == "AdsAgent"
    assert rows[0]["status"] == "ok"
