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


def _chips(html: str) -> list[str]:
    """Text of every example chip, with the space marker turned back into a space."""
    chips = re.findall(r'<code class="chip">(.*?)</code>', html)
    return [chip.replace('<span class="sp">␣</span>', " ") for chip in chips]


def _report_with_examples(examples: list[str]) -> dict:
    column = {
        "column": "phone",
        "declared_type": "TEXT",
        "pii_type": "phone",
        "empty_rate": 0.0,
        "unique_rate": 1.0,
        "format_rate": 0.0,
        "score": 50,
        "invalid_examples": examples,
    }
    return {
        "database": "x.db",
        "scanned_at": "now",
        "version": "0",
        "summary": {"tables": 1, "columns": 1, "pii_columns": 1},
        "tables": [{"name": "t", "rows": 3, "columns": [column]}],
    }


def test_each_invalid_example_is_its_own_chip():
    html = render_html(_report_with_examples(["999 999", "aaa", " 99  a "]))
    assert _chips(html) == ["999 999", "aaa", " 99  a "]


def test_spaces_in_a_chip_are_drawn_as_a_marker():
    html = render_html(_report_with_examples([" 99  a "]))
    chip = re.search(r'<code class="chip">(.*?)</code>', html).group(1)
    assert chip.count("␣") == 4
    assert " " not in re.sub(r"<[^>]+>", "", chip)


def test_chip_text_is_escaped():
    html = render_html(_report_with_examples(["<aa>&99"]))
    assert '<code class="chip">&lt;aa&gt;&amp;99</code>' in html


def test_column_without_examples_has_no_chips(sample_db):
    html = render_html(_report_with_examples([]))
    assert '<code class="chip">' not in html


def test_html_examples_show_only_the_shape(sample_db):
    examples = _chips(render_html(scan_database(sample_db)))
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
