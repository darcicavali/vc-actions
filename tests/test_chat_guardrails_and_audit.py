"""Tests for the smaller chat modules: guardrails + audit."""

from __future__ import annotations

import pytest

from chat import audit, guardrails


# ---- guardrails -------------------------------------------------------


def test_destructive_tools_set_is_currently_empty():
    """The launched bot ships with no destructive tools. When we add
    one, this test breaks intentionally so the change gets reviewed."""
    assert guardrails.DESTRUCTIVE_TOOLS == frozenset()


def test_needs_confirmation_is_false_for_read_tools():
    assert guardrails.needs_confirmation("read_sheet_tab") is False
    assert guardrails.needs_confirmation("read_baseline") is False


def test_needs_confirmation_is_false_for_append_only_writes():
    """Append-only writes execute immediately. The audit tab is the
    safety net; Sheets revision history is the rollback."""
    assert guardrails.needs_confirmation("add_lesson") is False
    assert guardrails.needs_confirmation("note_for_next_run") is False


def test_needs_confirmation_when_tool_is_in_destructive_set(monkeypatch):
    monkeypatch.setattr(
        guardrails, "DESTRUCTIVE_TOOLS", frozenset({"delete_lesson"})
    )
    assert guardrails.needs_confirmation("delete_lesson") is True
    assert guardrails.needs_confirmation("read_sheet_tab") is False


def test_confirmation_prompt_includes_tool_name(monkeypatch):
    prompt = guardrails.confirmation_prompt(
        "delete_lesson", {"category": "hard_rule", "lesson": "x"}
    )
    assert "delete_lesson" in prompt
    assert "yes" in prompt.lower()


# ---- audit ------------------------------------------------------------


def test_audit_log_action_writes_row_to_bot_actions(sheets):
    audit.log_action(
        sheets,
        transport="telegram",
        conversation_id="darci",
        tool_name="add_lesson",
        tool_args={"agent_target": "AdsAgent", "category": "hard_rule", "lesson": "x"},
        result_summary="Lesson added.",
        requires_confirmation=False,
        confirmed=False,
    )
    rows = sheets.read_tab("Bot Actions")
    assert len(rows) == 1
    r = rows[0]
    assert r["transport"] == "telegram"
    assert r["conversation_id"] == "darci"
    assert r["tool_name"] == "add_lesson"
    assert r["requires_confirmation"] == "no"
    assert r["confirmed"] == "n/a"


def test_audit_log_swallows_sheet_errors(monkeypatch, sheets, caplog):
    """Audit failures must NOT crash the bot. We log a warning and move on."""

    def boom(*a, **kw):
        raise RuntimeError("sheets blew up")

    monkeypatch.setattr(sheets, "append_row", boom)
    # Should NOT raise.
    audit.log_action(
        sheets,
        transport="telegram",
        conversation_id="darci",
        tool_name="add_lesson",
        tool_args={},
        result_summary="x",
        requires_confirmation=False,
        confirmed=False,
    )


def test_audit_truncates_long_result_summary(sheets):
    huge = "x" * 5000
    audit.log_action(
        sheets,
        transport="streamlit",
        conversation_id="darci",
        tool_name="read_sheet_tab",
        tool_args={"tab_name": "Big"},
        result_summary=huge,
        requires_confirmation=False,
        confirmed=False,
    )
    rows = sheets.read_tab("Bot Actions")
    assert len(rows[0]["result_summary"]) <= 600  # generous bound: includes the truncation
