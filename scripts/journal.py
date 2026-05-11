"""BUILD_JOURNAL.md helpers.

Per v5 §Part 4: append-only, one entry per session. This module gives both
Claude Code (during build) and any runtime tooling a single place to append
a structured entry. Existing entries are never modified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


JOURNAL_PATH_DEFAULT = Path(__file__).resolve().parent.parent / "BUILD_JOURNAL.md"


@dataclass
class JournalEntry:
    session_number: int
    title: str
    attempted: list[str] = field(default_factory=list)
    worked: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    learnings: list[str] = field(default_factory=list)
    entry_date: date = field(default_factory=date.today)

    def render(self) -> str:
        def bullets(items: list[str]) -> str:
            if not items:
                return "- (none)"
            return "\n".join(f"- {x}" for x in items)

        return (
            f"## {self.entry_date.isoformat()} — Session {self.session_number}: {self.title}\n\n"
            f"### What was attempted\n\n{bullets(self.attempted)}\n\n"
            f"### What worked\n\n{bullets(self.worked)}\n\n"
            f"### What failed / had to retry\n\n{bullets(self.failed)}\n\n"
            f"### Decisions made\n\n{bullets(self.decisions)}\n\n"
            f"### Open questions\n\n{bullets(self.open_questions)}\n\n"
            f"### Learnings for future sessions\n\n{bullets(self.learnings)}\n\n"
            "---\n"
        )


def append_entry(entry: JournalEntry, path: Path | None = None) -> Path:
    p = path or JOURNAL_PATH_DEFAULT
    text = p.read_text() if p.exists() else "# Build Journal\n\n"
    if not text.endswith("\n"):
        text += "\n"
    if not text.endswith("\n\n"):
        text += "\n"
    p.write_text(text + entry.render())
    return p


def read_journal(path: Path | None = None) -> str:
    p = path or JOURNAL_PATH_DEFAULT
    return p.read_text() if p.exists() else ""
