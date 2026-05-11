from datetime import date

from scripts.journal import JournalEntry, append_entry, read_journal


def test_append_entry_creates_file_if_missing(tmp_path):
    p = tmp_path / "BUILD_JOURNAL.md"
    entry = JournalEntry(
        session_number=1,
        title="Initial scaffold",
        attempted=["scaffold repo"],
        worked=["dataclass memos"],
        failed=["wrong model id"],
        decisions=["use dataclasses"],
        open_questions=["dry-run flag?"],
        learnings=["pin SDK version"],
        entry_date=date(2026, 5, 11),
    )
    append_entry(entry, path=p)
    text = p.read_text()
    assert "## 2026-05-11 — Session 1: Initial scaffold" in text
    assert "scaffold repo" in text
    assert "pin SDK version" in text


def test_append_entry_preserves_prior_content(tmp_path):
    p = tmp_path / "BUILD_JOURNAL.md"
    p.write_text("# Build Journal\n\nExisting content.\n")
    entry = JournalEntry(
        session_number=2,
        title="Second",
        attempted=["x"],
        entry_date=date(2026, 5, 12),
    )
    append_entry(entry, path=p)
    text = p.read_text()
    assert "Existing content." in text
    assert "Session 2: Second" in text
    # The old content should appear before the new entry.
    assert text.index("Existing content.") < text.index("Session 2: Second")


def test_read_journal_empty_when_missing(tmp_path):
    p = tmp_path / "missing.md"
    assert read_journal(path=p) == ""


def test_render_handles_empty_sections():
    entry = JournalEntry(session_number=99, title="Stub")
    out = entry.render()
    # Every section header is present even when empty.
    for header in [
        "What was attempted",
        "What worked",
        "What failed / had to retry",
        "Decisions made",
        "Open questions",
        "Learnings for future sessions",
    ]:
        assert header in out
    assert "(none)" in out
