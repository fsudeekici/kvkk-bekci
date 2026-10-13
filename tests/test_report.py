import json
import re

from kvkk_bekci.report import render_html, write_reports
from kvkk_bekci.scan import scan_database
from kvkk_bekci.validators import is_empty

from conftest import column_values

PII_COLUMNS = [
    ("customers", "full_name"),
    ("customers", "tc_no"),
    ("customers", "phone"),
    ("customers", "email"),
    ("customers", "iban"),
]


def test_writes_json_and_html(sample_db, tmp_path):
    report = scan_database(sample_db)
    json_path, html_path = write_reports(report, tmp_path / "out" / "nested")

    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    assert html_path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_json_has_expected_fields(sample_db, tmp_path):
    json_path, _ = write_reports(scan_database(sample_db), tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))

    assert {"tool", "version", "database", "scanned_at", "summary", "tables"} <= data.keys()
    column = data["tables"][0]["columns"][0]
    assert {"column", "pii_type", "empty_rate", "unique_rate", "format_rate", "score", "invalid_examples"} <= column.keys()


def test_html_lists_every_column(sample_db):
    report = scan_database(sample_db)
    html = render_html(report)
    for table in report["tables"]:
        assert table["name"] in html
        for column in table["columns"]:
            assert f"<td>{column['column']}</td>" in html


def test_html_escapes_names():
    report = {
        "database": "<x>.db",
        "scanned_at": "now",
        "version": "0",
        "summary": {"tables": 1, "columns": 1, "pii_columns": 0},
        "tables": [
            {
                "name": "t<script>",
                "rows": 1,
                "columns": [
                    {
                        "column": "a&b",
                        "declared_type": "",
                        "pii_type": None,
                        "empty_rate": 0.0,
                        "unique_rate": 1.0,
                        "format_rate": None,
                        "score": 100,
                        "invalid_examples": [],
                    }
                ],
            }
        ],
    }
    html = render_html(report)
    assert "t&lt;script&gt;" in html and "a&amp;b" in html
    assert "<script>" not in html


def test_html_examples_show_only_the_shape(sample_db):
    examples = re.findall(r"<code>(.*?)</code>", render_html(scan_database(sample_db)))
    assert examples
    for example in examples:
        assert not re.search(r"[0-8]", example)
        assert all(c == "a" for c in example if c.isalpha())


def test_reports_hold_no_raw_pii(sample_db, tmp_path):
    json_path, html_path = write_reports(scan_database(sample_db), tmp_path)
    text = json_path.read_text(encoding="utf-8") + html_path.read_text(encoding="utf-8")

    for table, column in PII_COLUMNS:
        for value in column_values(sample_db, table, column):
            if not is_empty(value) and any(c.isalnum() for c in value):
                assert value not in text
