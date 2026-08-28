from app.exporting import flatten_record, rows_to_csv, rows_to_jsonl


def test_flatten_record_uses_dotted_keys():
    assert flatten_record({"order": {"ticker": "AAPL_US_EQ", "fill": {"price": 201.5}}}) == {
        "order.ticker": "AAPL_US_EQ",
        "order.fill.price": 201.5,
    }


def test_csv_export_escapes_spreadsheet_formula_prefixes():
    csv_text = rows_to_csv([{"ticker": "=1+1", "quantity": 2.0}])
    assert "'=1+1" in csv_text
    assert "quantity" in csv_text


def test_jsonl_export_emits_one_record_per_line():
    text = rows_to_jsonl([{"ticker": "A"}, {"ticker": "B"}])
    assert text.count("\n") == 2
    assert '"ticker":"A"' in text
    assert '"ticker":"B"' in text
