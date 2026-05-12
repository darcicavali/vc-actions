"""Confirmation gates for destructive bot actions.

The bot has full read/write to Sheets, but writes split into two classes:

- **Append-only** (lessons, outcomes, notes for next run): no confirmation
  needed. Worst case is a stray row Darci can delete in one click.
- **Mutating** (overwriting baseline sections, mass deletes): always
  requires confirmation. Bot replies "About to do X. Reply 'yes' to
  confirm." and waits.

The set of tools requiring confirmation is *defined here, not at the
tool definition site* — so a future change can add or remove gating
without editing every tool signature. Keep this list short and the
membership obvious.
"""

from __future__ import annotations

# Append-only writes do NOT appear here. Add a tool only if it can
# overwrite or delete user data.
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        # Reserved for future tools that overwrite curated data.
        # Examples we'll add as the bot grows:
        # "update_baseline_section",  # overwrites a curated baseline row
        # "delete_lesson",             # removes a hard rule
        # "reset_outcomes_for_week",   # mass-clears
    }
)


def needs_confirmation(tool_name: str, tool_args: dict | None = None) -> bool:
    """Return True if the bot must surface a confirmation prompt to the
    user before executing this tool call. `tool_args` is currently
    unused; it's plumbed through so future rules can gate by argument
    (e.g. "delete_lesson with category=hard_rule needs confirmation").
    """
    return tool_name in DESTRUCTIVE_TOOLS


def confirmation_prompt(tool_name: str, tool_args: dict) -> str:
    """One-line summary the bot shows before executing a destructive
    action. Kept generic — the model can prepend a richer explanation
    in the same turn.
    """
    args_preview = ", ".join(f"{k}={v!r}" for k, v in list(tool_args.items())[:3])
    return f"About to run `{tool_name}({args_preview})`. Reply 'yes' to confirm, or anything else to cancel."
