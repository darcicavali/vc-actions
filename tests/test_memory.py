from datetime import datetime, timezone

from scripts.memory import (
    format_lessons,
    format_outcomes,
    format_past_memos,
    load_agent_memory,
    render_memory_block,
)
from scripts.sheets_client import MemoRow


def test_load_empty_memory(sheets):
    mem = load_agent_memory(sheets, "AdsAgent")
    assert mem.is_empty
    assert mem.lessons == []
    assert mem.past_memos == []
    assert mem.past_outcomes == []


def test_empty_memory_renders_clean_block(sheets):
    mem = load_agent_memory(sheets, "AdsAgent")
    block = render_memory_block(mem)
    assert "(no active lessons)" in block
    assert "(no prior memos)" in block
    assert "(no recorded outcomes)" in block


def test_load_with_lessons_and_memos(sheets):
    today = datetime.now(timezone.utc).date().isoformat()
    sheets.append_row(
        "Agent Knowledge",
        [today, "AdsAgent", "vendor", "no Maria reorder", "TRUE", "", ""],
    )
    sheets.append_memo(
        MemoRow(
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            agent="AdsAgent",
            summary="cold healthy",
            diagnosis="dx",
            recommendations=[
                {
                    "priority": 1,
                    "action": "scale Prospect +$10/day",
                    "impact_dollars_per_week": 40,
                    "confidence": "high",
                }
            ],
            watch_list=["freq creep"],
            data_quality="high",
            raw_response_truncated="raw",
        )
    )
    mem = load_agent_memory(sheets, "AdsAgent")
    assert len(mem.lessons) == 1
    assert len(mem.past_memos) == 1
    block = render_memory_block(mem)
    assert "no Maria reorder" in block
    assert "scale Prospect" in block
    assert "(no recorded outcomes)" in block


def test_format_lessons_uses_scope_tag():
    from scripts.sheets_client import LessonRow

    lessons = [
        LessonRow("2026-05-11", "ALL", "strategy", "no TikTok", True, "", ""),
        LessonRow("2026-05-11", "AdsAgent", "vendor", "no Maria", True, "2026-12-31", ""),
    ]
    out = format_lessons(lessons)
    assert "(ALL)" in out
    assert "(you)" in out
    assert "expires 2026-12-31" in out


def test_format_past_memos_includes_recommendations():
    memos = [
        MemoRow(
            generated_at="2026-05-04T08:00:00+00:00",
            agent="AdsAgent",
            summary="ok",
            diagnosis="dx",
            recommendations=[
                {"priority": 1, "action": "A1", "impact_dollars_per_week": 100, "confidence": "high"}
            ],
            watch_list=[],
            data_quality="high",
            raw_response_truncated="",
        )
    ]
    out = format_past_memos(memos)
    assert "A1" in out
    assert "P1" in out
