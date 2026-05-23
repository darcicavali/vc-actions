"""Email body formatter for the weekly digest.

Takes an `ActionPlan` and produces the plain-text body that Resend sends
to Darci on Monday mornings. Designed to be read on a phone first — short
lines, key sections on top, no jargon.

If the GoalsAgent populated `summary_email_body` we use that as the body
and just wrap it with the structured sections; otherwise we build the
whole body from the structured fields.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.goals_agent import ActionPlan


SUBJECT_PREFIX = "VC Weekly Plan"


@dataclass
class FormattedEmail:
    subject: str
    text: str


def _fmt_money(value) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    if n >= 1000 or n <= -1000:
        return f"${n:,.0f}"
    return f"${n:,.2f}"


def _pace_block(pace: dict | None) -> str:
    if not isinstance(pace, dict) or not pace:
        return ""
    ytd = pace.get("ytd_revenue")
    target = pace.get("target_ytd")
    gap = pace.get("gap")
    signal = pace.get("pace_signal") or ""
    needed = pace.get("needed_per_week")
    weeks = pace.get("weeks_remaining")
    lines = ["PACE STATUS"]
    if ytd is not None and target is not None:
        lines.append(f"YTD {_fmt_money(ytd)} vs target {_fmt_money(target)} ({signal})")
    if gap is not None:
        lines.append(f"Gap: {_fmt_money(gap)}")
    if needed is not None and weeks is not None:
        lines.append(f"Needed: {_fmt_money(needed)}/wk over {weeks} weeks")
    return "\n".join(lines)


def _actions_block(actions: list[dict] | None) -> str:
    if not actions:
        return ""
    lines = ["THIS WEEK'S ACTIONS"]
    for i, a in enumerate(actions, start=1):
        if not isinstance(a, dict):
            continue
        action = str(a.get("action", "")).strip()
        if not action:
            continue
        day = str(a.get("day", "")).strip()
        agent = str(a.get("agent_source", "")).strip()
        impact = a.get("impact_dollars_per_week")
        tail_parts = [p for p in [day, agent] if p]
        if impact is not None:
            try:
                tail_parts.append(f"{_fmt_money(impact)}/wk")
            except Exception:
                pass
        tail = " · ".join(tail_parts)
        suffix = f" ({tail})" if tail else ""
        lines.append(f"{i}. {action}{suffix}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _watch_block(watch_list: list[str] | None) -> str:
    if not watch_list:
        return ""
    lines = ["WATCH NEXT WEEK"]
    for w in watch_list:
        if w:
            lines.append(f"- {w}")
    return "\n".join(lines) if len(lines) > 1 else ""


def format_digest(plan: ActionPlan, *, week_label: str | None = None) -> FormattedEmail:
    """Build subject + plain-text body for the Monday digest email."""
    label = week_label or plan.generated_at[:10]
    subject = f"{SUBJECT_PREFIX} — {label}"

    blocks: list[str] = []
    if plan.one_thing_this_week:
        blocks.append(f"ONE THING THIS WEEK\n{plan.one_thing_this_week}")
    if plan.summary:
        blocks.append(f"SUMMARY\n{plan.summary}")
    pace = _pace_block(plan.pace_status)
    if pace:
        blocks.append(pace)
    actions = _actions_block(plan.sequenced_actions)
    if actions:
        blocks.append(actions)
    watch = _watch_block(plan.watch_list)
    if watch:
        blocks.append(watch)

    # If the coordinator produced its own narrative body, append it at the
    # bottom for readers who want the full reasoning rather than the
    # structured digest.
    if plan.summary_email_body and plan.summary_email_body.strip():
        blocks.append(f"---\n{plan.summary_email_body.strip()}")

    text = "\n\n".join(b for b in blocks if b).strip() + "\n"
    return FormattedEmail(subject=subject, text=text)
