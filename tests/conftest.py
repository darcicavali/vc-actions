"""Shared test fixtures.

Strategy: hand-rolled fake gspread surface (FakeSpreadsheet / FakeWorksheet)
that conforms to the slice of the gspread API the SheetsClient touches.
This avoids pulling in `unittest.mock`-heavy plumbing and keeps tests
behaviorally honest.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure repo root is importable when running pytest from any cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import gspread  # noqa: E402

from scripts.sheets_client import SheetsClient  # noqa: E402


class FakeWorksheet:
    def __init__(self, title: str):
        self.title = title
        self._rows: list[list] = []  # row 1 is headers if set

    def row_values(self, row: int) -> list:
        if row - 1 < 0 or row - 1 >= len(self._rows):
            return []
        return list(self._rows[row - 1])

    def update(self, cell: str, values: list[list]) -> None:
        if cell != "A1":
            raise NotImplementedError(f"FakeWorksheet.update only supports A1, got {cell}")
        if not values:
            return
        # Replace from row 1 down. Truncates anything past the new content.
        self._rows = [list(r) for r in values]

    def append_row(self, row: list, value_input_option: str = "USER_ENTERED") -> None:
        self._rows.append(list(row))

    def get_all_records(self) -> list[dict]:
        if len(self._rows) < 2:
            return []
        headers = self._rows[0]
        out = []
        for r in self._rows[1:]:
            d = {}
            for i, h in enumerate(headers):
                d[h] = r[i] if i < len(r) else ""
            out.append(d)
        return out


class FakeSpreadsheet:
    def __init__(self):
        self._worksheets: dict[str, FakeWorksheet] = {}

    def worksheet(self, title: str) -> FakeWorksheet:
        if title not in self._worksheets:
            raise gspread.exceptions.WorksheetNotFound(title)
        return self._worksheets[title]

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        ws = FakeWorksheet(title)
        self._worksheets[title] = ws
        return ws

    def worksheets(self) -> list[FakeWorksheet]:
        return list(self._worksheets.values())


@pytest.fixture
def fake_spreadsheet() -> FakeSpreadsheet:
    return FakeSpreadsheet()


@pytest.fixture
def sheets(fake_spreadsheet) -> SheetsClient:
    client = SheetsClient(fake_spreadsheet)
    client.ensure_all_tabs()
    return client
