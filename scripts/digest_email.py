"""Email body formatter for the weekly digest.

Produces BOTH a plain-text body (always) and an HTML body (visual) from an
ActionPlan. Resend sends both; email clients that block HTML fall back to text.

Design goals (from Darci's 2026-05-28 feedback):
- Lead with a visual scorecard of the headline numbers, color-coded.
- Show a real chart of pace-to-goal (rendered via QuickChart — a URL-based
  image service, so no image hosting on our side; renders in Gmail).
- De-duplicate: the old email printed the structured sections AND the
  coordinator's free-form summary_email_body — same plan twice. We now build
  ONE clean layout from the structured fields. summary_email_body is dropped
  from the email (it still lives in the Action Plan sheet tab for reference).
- Cap actions shown in the email; the full plan is always in the sheet.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass

from agents.goals_agent import ActionPlan


SUBJECT_PREFIX = "VC Weekly Plan"

# How many sequenced actions to show in the email body before linking to the
# sheet for the rest. Keeps the Monday email scannable.
MAX_ACTIONS_IN_EMAIL = 5

# Status -> (text label color, background tint) for the HTML scorecard.
_STATUS_COLORS = {
    "good": ("#1a7f37", "#e6f4ea"),
    "warn": ("#9a6700", "#fff8e1"),
    "bad": ("#d1242f", "#ffebe9"),
    "": ("#1f2328", "#f6f8fa"),
}
_TREND_ARROWS = {"up": "↑", "down": "↓", "flat": "→", "": ""}


@dataclass
class FormattedEmail:
    subject: str
    text: str
    html: str


def _fmt_money(value) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1000:
        return f"{sign}${n:,.0f}"
    return f"{sign}${n:,.2f}"


# ---------- plain text ----------

def _pace_block_text(pace: dict | None) -> str:
    if not isinstance(pace, dict) or not pace:
        return ""
    ytd, target, gap = pace.get("ytd_revenue"), pace.get("target_ytd"), pace.get("gap")
    signal = pace.get("pace_signal") or ""
    needed, weeks = pace.get("needed_per_week"), pace.get("weeks_remaining")
    lines = ["PACE"]
    if ytd is not None and target is not None:
        lines.append(f"YTD {_fmt_money(ytd)} vs target {_fmt_money(target)} ({signal})")
    if gap is not None:
        lines.append(f"Gap: {_fmt_money(gap)}")
    if needed is not None and weeks is not None:
        lines.append(f"Needed: {_fmt_money(needed)}/wk over {weeks} weeks")
    return "\n".join(lines)


def _metrics_block_text(metrics: list[dict]) -> str:
    if not metrics:
        return ""
    lines = ["KEY NUMBERS"]
    for m in metrics:
        label = str(m.get("label", "")).strip()
        value = str(m.get("value", "")).strip()
        arrow = _TREND_ARROWS.get(str(m.get("trend", "")), "")
        ctx = str(m.get("context", "")).strip()
        if not label:
            continue
        tail = f" — {ctx}" if ctx else ""
        lines.append(f"- {label}: {value} {arrow}{tail}".rstrip())
    return "\n".join(lines) if len(lines) > 1 else ""


def _actions_block_text(actions: list[dict]) -> str:
    if not actions:
        return ""
    shown = actions[:MAX_ACTIONS_IN_EMAIL]
    lines = ["THIS WEEK'S ACTIONS"]
    for i, a in enumerate(shown, start=1):
        if not isinstance(a, dict):
            continue
        action = str(a.get("action", "")).strip()
        if not action:
            continue
        bits = [str(a.get("day", "")).strip(), str(a.get("agent_source", "")).strip()]
        impact = a.get("impact_dollars_per_week")
        if impact:
            bits.append(f"{_fmt_money(impact)}/wk")
        tail = " · ".join(b for b in bits if b)
        lines.append(f"{i}. {action}" + (f" ({tail})" if tail else ""))
    extra = len(actions) - len(shown)
    if extra > 0:
        lines.append(f"...and {extra} more in the Action Plan tab.")
    return "\n".join(lines) if len(lines) > 1 else ""


def _list_block_text(title: str, items) -> str:
    if not items:
        return ""
    lines = [title]
    for it in items:
        if isinstance(it, dict):
            # conflicts_resolved entries
            c, r = it.get("conflict", ""), it.get("resolution", "")
            if c or r:
                lines.append(f"- {c} → {r}")
        elif it:
            lines.append(f"- {it}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _build_text(plan: ActionPlan) -> str:
    blocks = []
    if plan.one_thing_this_week:
        blocks.append(f"ONE THING THIS WEEK\n{plan.one_thing_this_week}")
    if plan.summary:
        blocks.append(f"SUMMARY\n{plan.summary}")
    for b in (
        _metrics_block_text(plan.key_metrics),
        _pace_block_text(plan.pace_status),
        _actions_block_text(plan.sequenced_actions),
        _list_block_text("CONFLICTS RESOLVED", plan.conflicts_resolved
                         if isinstance(plan.conflicts_resolved, list) else []),
        _list_block_text("WATCH NEXT WEEK", plan.watch_list),
    ):
        if b:
            blocks.append(b)
    return "\n\n".join(blocks).strip() + "\n"


# ---------- chart ----------

def _pace_chart_url(pace: dict | None) -> str | None:
    """A QuickChart horizontal bar comparing YTD to target. URL-based image —
    renders in email without us hosting anything. Returns None if no data."""
    if not isinstance(pace, dict):
        return None
    ytd, target = pace.get("ytd_revenue"), pace.get("target_ytd")
    try:
        ytd_f, target_f = float(ytd), float(target)
    except (TypeError, ValueError):
        return None
    if target_f <= 0:
        return None
    config = {
        "type": "horizontalBar",
        "data": {
            "labels": ["YTD", "Goal"],
            "datasets": [{
                "data": [round(ytd_f), round(target_f)],
                "backgroundColor": ["#2da44e", "#d0d7de"],
            }],
        },
        "options": {
            "legend": {"display": False},
            "title": {"display": True, "text": "Revenue: YTD vs annual goal"},
            "scales": {"xAxes": [{"ticks": {"beginAtZero": True}}]},
        },
    }
    encoded = urllib.parse.quote(json.dumps(config))
    return f"https://quickchart.io/chart?w=520&h=180&bkg=white&c={encoded}"


def _parse_num(value) -> float | None:
    """Strip $, %, commas, whitespace and parse a float. None on failure."""
    if value is None:
        return None
    s = str(value).strip().replace("$", "").replace(",", "").replace("%", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _week_label(row: dict) -> str:
    """Short MM/DD label from a Weekly Summary 'Week Start' cell."""
    raw = str(row.get("Week Start", "")).strip()
    # Accept YYYY-MM-DD or similar; fall back to the raw string.
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[5:10].replace("-", "/")
    return raw[:5]


def weekly_trends(rows: list[dict], last_n: int = 12) -> list[tuple[str, list, list]]:
    """From Weekly Summary rows, compute trend series for the email charts.

    Returns a list of (title, labels, values). All metrics are computed from
    raw columns (not the unreliable rounded Margin % column):
      - Net Sales (weekly revenue)
      - Return rate % = Returns / Gross Sales * 100
      - Margin %      = Gross Profit / Net Sales * 100
    A series is skipped if fewer than 2 valid points exist.
    """
    if not rows:
        return []
    recent = rows[-last_n:]
    labels = [_week_label(r) for r in recent]

    def series(fn) -> list:
        return [fn(r) for r in recent]

    def ret_rate(r):
        gross = _parse_num(r.get("Gross Sales"))
        returns = _parse_num(r.get("Returns"))
        if gross and gross > 0 and returns is not None:
            return round(returns / gross * 100, 1)
        return None

    def margin(r):
        net = _parse_num(r.get("Net Sales"))
        gp = _parse_num(r.get("Gross Profit"))
        if net and net > 0 and gp is not None:
            return round(gp / net * 100, 1)
        return None

    candidates = [
        ("Weekly net sales ($)", series(lambda r: _parse_num(r.get("Net Sales")))),
        ("Return rate (%)", series(ret_rate)),
        ("Gross margin (%)", series(margin)),
    ]
    out = []
    for title, vals in candidates:
        if sum(1 for v in vals if v is not None) >= 2:
            out.append((title, labels, vals))
    return out


def _trend_chart_url(title: str, labels: list, values: list, color: str) -> str:
    config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": title,
                "data": values,
                "borderColor": color,
                "backgroundColor": color,
                "fill": False,
                "spanGaps": True,
                "pointRadius": 2,
            }],
        },
        "options": {
            "legend": {"display": False},
            "title": {"display": True, "text": title},
        },
    }
    encoded = urllib.parse.quote(json.dumps(config))
    return f"https://quickchart.io/chart?w=520&h=200&bkg=white&c={encoded}"


# ---------- html ----------

def _esc(s) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _scorecard_html(metrics: list[dict]) -> str:
    if not metrics:
        return ""
    cells = []
    for m in metrics:
        label = _esc(m.get("label", ""))
        value = _esc(m.get("value", ""))
        ctx = _esc(m.get("context", ""))
        status = str(m.get("status", "")).lower()
        fg, bg = _STATUS_COLORS.get(status, _STATUS_COLORS[""])
        arrow = _TREND_ARROWS.get(str(m.get("trend", "")), "")
        cells.append(
            f'<td style="padding:6px;width:33%;vertical-align:top;">'
            f'<div style="background:{bg};border-radius:8px;padding:12px;">'
            f'<div style="font-size:12px;color:#57606a;">{label}</div>'
            f'<div style="font-size:22px;font-weight:700;color:{fg};">{value} '
            f'<span style="font-size:16px;">{arrow}</span></div>'
            f'<div style="font-size:11px;color:#57606a;">{ctx}</div>'
            f'</div></td>'
        )
    # 3 cards per row
    rows = []
    for i in range(0, len(cells), 3):
        rows.append("<tr>" + "".join(cells[i:i + 3]) + "</tr>")
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;margin:8px 0;">' + "".join(rows) + "</table>"
    )


def _pace_bar_html(pace: dict | None) -> str:
    if not isinstance(pace, dict):
        return ""
    ytd, target, gap = pace.get("ytd_revenue"), pace.get("target_ytd"), pace.get("gap")
    try:
        pct = max(0, min(100, round(float(ytd) / float(target) * 100)))
    except (TypeError, ValueError, ZeroDivisionError):
        return ""
    gap_txt = f" · gap {_fmt_money(gap)}" if gap is not None else ""
    return (
        f'<div style="margin:8px 0;">'
        f'<div style="font-size:13px;color:#57606a;margin-bottom:4px;">'
        f'Pace to goal: {_fmt_money(ytd)} of {_fmt_money(target)} ({pct}%){gap_txt}</div>'
        f'<div style="background:#d0d7de;border-radius:6px;height:14px;width:100%;">'
        f'<div style="background:#2da44e;height:14px;border-radius:6px;width:{pct}%;"></div>'
        f'</div></div>'
    )


def _section_html(title: str, inner: str) -> str:
    if not inner:
        return ""
    return (
        f'<h3 style="font-size:14px;color:#1f2328;margin:18px 0 6px;'
        f'border-bottom:1px solid #d0d7de;padding-bottom:4px;">{title}</h3>{inner}'
    )


def _actions_html(actions: list[dict]) -> str:
    if not actions:
        return ""
    shown = actions[:MAX_ACTIONS_IN_EMAIL]
    items = []
    for a in shown:
        if not isinstance(a, dict):
            continue
        action = _esc(a.get("action", ""))
        if not action:
            continue
        bits = [_esc(a.get("day", "")), _esc(a.get("agent_source", ""))]
        impact = a.get("impact_dollars_per_week")
        if impact:
            bits.append(_esc(f"{_fmt_money(impact)}/wk"))
        tail = " · ".join(b for b in bits if b)
        meta = f'<span style="color:#57606a;font-size:12px;"> ({tail})</span>' if tail else ""
        items.append(f'<li style="margin:6px 0;">{action}{meta}</li>')
    extra = len(actions) - len(shown)
    more = (
        f'<li style="margin:6px 0;color:#57606a;">…and {extra} more in the '
        f'Action Plan tab.</li>' if extra > 0 else ""
    )
    return f'<ol style="padding-left:20px;margin:4px 0;">{"".join(items)}{more}</ol>'


def _bullets_html(items, kind: str = "plain") -> str:
    if not items:
        return ""
    lis = []
    for it in items:
        if kind == "conflict" and isinstance(it, dict):
            c, r = _esc(it.get("conflict", "")), _esc(it.get("resolution", ""))
            if c or r:
                lis.append(f'<li style="margin:6px 0;">{c} → <b>{r}</b></li>')
        elif it:
            lis.append(f'<li style="margin:6px 0;">{_esc(it)}</li>')
    return f'<ul style="padding-left:20px;margin:4px 0;">{"".join(lis)}</ul>' if lis else ""


_TREND_COLORS = ["#0969da", "#d1242f", "#9a6700"]


def _trends_html(weekly_rows: list[dict] | None) -> str:
    if not weekly_rows:
        return ""
    imgs = []
    for i, (title, labels, values) in enumerate(weekly_trends(weekly_rows)):
        url = _trend_chart_url(title, labels, values, _TREND_COLORS[i % len(_TREND_COLORS)])
        imgs.append(
            f'<div style="margin:10px 0;"><img src="{url}" width="520" '
            f'alt="{_esc(title)}" style="max-width:100%;border-radius:8px;"/></div>'
        )
    if not imgs:
        return ""
    return _section_html("Trends (last 12 weeks)", "".join(imgs))


def _build_html(plan: ActionPlan, weekly_rows: list[dict] | None = None) -> str:
    chart_url = _pace_chart_url(plan.pace_status)
    chart_html = (
        f'<div style="margin:10px 0;"><img src="{chart_url}" width="520" '
        f'alt="Revenue pace chart" style="max-width:100%;border-radius:8px;"/></div>'
        if chart_url else ""
    )
    one_thing = (
        f'<div style="background:#0969da;color:#fff;border-radius:8px;padding:14px;'
        f'margin:8px 0;"><div style="font-size:12px;opacity:.85;">ONE THING THIS WEEK</div>'
        f'<div style="font-size:16px;font-weight:600;margin-top:4px;">'
        f'{_esc(plan.one_thing_this_week)}</div></div>'
        if plan.one_thing_this_week else ""
    )
    conflicts = plan.conflicts_resolved if isinstance(plan.conflicts_resolved, list) else []
    body = "".join([
        one_thing,
        _scorecard_html(plan.key_metrics),
        _pace_bar_html(plan.pace_status),
        chart_html,
        _section_html("Summary", f'<p style="margin:4px 0;">{_esc(plan.summary)}</p>'
                      if plan.summary else ""),
        _section_html("This week's actions", _actions_html(plan.sequenced_actions)),
        _section_html("Conflicts resolved", _bullets_html(conflicts, "conflict")),
        _section_html("Watch next week", _bullets_html(plan.watch_list)),
        _trends_html(weekly_rows),
    ])
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:600px;margin:0 auto;color:#1f2328;font-size:14px;line-height:1.5;">'
        f'{body}'
        '<p style="color:#8c959f;font-size:11px;margin-top:20px;">'
        'Full plan and history live in the Action Plan tab of your dashboard.</p>'
        '</div>'
    )


def format_digest(
    plan: ActionPlan,
    *,
    week_label: str | None = None,
    weekly_rows: list[dict] | None = None,
) -> FormattedEmail:
    label = week_label or plan.generated_at[:10]
    subject = f"{SUBJECT_PREFIX} — {label}"
    return FormattedEmail(
        subject=subject,
        text=_build_text(plan),
        html=_build_html(plan, weekly_rows=weekly_rows),
    )
