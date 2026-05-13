"""Bot Actions audit log — every bot-initiated write to Sheets lands here.

Sheets has a built-in revision history that lets Darci roll back any
write — this audit log is the human-readable index of what the bot did,
when, and why. Two columns matter most:

- `requires_confirmation`: whether the action passed through the
  confirmation gate (destructive actions only — see chat.guardrails).
- `confirmed`: whether Darci typed "yes" to it.

Append-only. Failures here must NOT block the bot from continuing the
conversation — we log the failure and move on.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


LOG = logging.getLogger(__name__)

_MAX_SUMMARY_CHARS = 500


def log_action(
    sheets,
    *,
    transport: str,
    conversation_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    result_summary: str,
    requires_confirmation: bool,
    confirmed: bool,
) -> None:
    """Append one row to the Bot Actions tab. Best-effort — swallows
    sheets errors so a transient API hiccup can't take down the bot.
    """
    summary = (result_summary or "")[:_MAX_SUMMARY_CHARS]
    try:
        sheets.append_row(
            "Bot Actions",
            [
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                transport,
                conversation_id,
                tool_name,
                json.dumps(tool_args, default=str)[:_MAX_SUMMARY_CHARS],
                summary,
                "yes" if requires_confirmation else "no",
                "yes" if confirmed else ("n/a" if not requires_confirmation else "no"),
            ],
        )
    except Exception as e:  # noqa: BLE001 — explicit best-effort
        LOG.warning("audit log write failed for %s: %s", tool_name, e)
