"""Tests for the Monday digest email formatter."""

from __future__ import annotations

from agents.goals_agent import ActionPlan
from scripts.digest_email import format_digest


def _plan(**overrides) -> ActionPlan:
    base = dict(
        generated_at="2026-05-25T13:00:00+00:00",
        summary="Week of 5/18 shows revenue recovery to $8.2k with margin stable at 48%.",
        one_thing_this_week="Pause RT-non-customer campaign — burned $280 with zero purchases.",
        pace_status={
            "ytd_revenue": 67767,
            "target_ytd": 124615,
            "gap": -56848,
            "pace_signal": "behind",
            "weeks_remaining": 31,
            "needed_per_week": 9426,
        },
        themes=[],
        sequenced_actions=[
            {
                "priority": 1,
                "day": "Monday",
                "action": "Pause RT-non-customer creative set",
                "agent_source": "AdsAgent",
                "effort": "low",
                "impact_dollars_per_week": 280,
                "depends_on": [],
            },
            {
                "priority": 2,
                "day": "Tuesday",
                "action": "Refresh PDP hero images for top 5 traffic products",
                "agent_source": "FunnelAgent",
                "effort": "medium",
                "impact_dollars_per_week": 400,
            },
        ],
        conflicts_resolved=[],
        watch_list=["RT-non-customer post-pause spend reallocation"],
        summary_email_body="",
    )
    base.update(overrides)
    return ActionPlan(**base)


def test_format_digest_basic():
    plan = _plan()
    out = format_digest(plan)

    assert out.subject == "VC Weekly Plan — 2026-05-25"
    assert "ONE THING THIS WEEK" in out.text
    assert "Pause RT-non-customer campaign" in out.text
    assert "SUMMARY" in out.text
    assert "Week of 5/18" in out.text
    assert "PACE STATUS" in out.text
    assert "$67,767" in out.text
    assert "$124,615" in out.text
    assert "$-56,848" in out.text or "-$56,848" in out.text
    assert "THIS WEEK'S ACTIONS" in out.text
    assert "1. Pause RT-non-customer creative set" in out.text
    assert "AdsAgent" in out.text
    assert "WATCH NEXT WEEK" in out.text
    assert out.text.endswith("\n")


def test_format_digest_with_week_label():
    plan = _plan()
    out = format_digest(plan, week_label="Week of 2026-05-18")
    assert out.subject == "VC Weekly Plan — Week of 2026-05-18"


def test_format_digest_handles_empty_sections():
    plan = _plan(
        pace_status={},
        sequenced_actions=[],
        watch_list=[],
        summary_email_body="",
    )
    out = format_digest(plan)
    assert "ONE THING THIS WEEK" in out.text
    assert "SUMMARY" in out.text
    assert "PACE STATUS" not in out.text
    assert "THIS WEEK'S ACTIONS" not in out.text
    assert "WATCH NEXT WEEK" not in out.text


def test_format_digest_appends_summary_email_body():
    plan = _plan(summary_email_body="Hey Darci, here's the long-form take...")
    out = format_digest(plan)
    assert "Hey Darci" in out.text
    assert "---" in out.text


def test_format_digest_actions_without_optional_fields():
    plan = _plan(
        sequenced_actions=[
            {"priority": 1, "action": "Just an action with no day or agent"},
        ]
    )
    out = format_digest(plan)
    assert "1. Just an action with no day or agent" in out.text
