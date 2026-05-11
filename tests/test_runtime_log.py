from scripts.runtime_log import RuntimeEntry, write_runtime_entry


def test_write_runtime_entry_appends_row(sheets, fake_spreadsheet):
    entry = RuntimeEntry(
        agent="AdsAgent",
        status="ok",
        duration_seconds=4.2,
        input_tokens=1234,
        output_tokens=567,
        cost_usd=0.012,
        key_insight="cold prospecting healthy",
        errors="",
    )
    write_runtime_entry(sheets, entry)
    rows = fake_spreadsheet.worksheet("Runtime Log").get_all_records()
    assert len(rows) == 1
    row = rows[0]
    assert row["agent"] == "AdsAgent"
    assert row["status"] == "ok"
    assert row["input_tokens"] == 1234
    assert row["key_insight"] == "cold prospecting healthy"
