import sqlite3

import pytest

from kvkk_bekci.scan import connect_readonly, outline, profile_column, quality_score, scan_database

from conftest import file_hash

EXPECTED_PII = {
    ("customers", "full_name"): "name",
    ("customers", "tc_no"): "tc_no",
    ("customers", "phone"): "phone",
    ("customers", "email"): "email",
    ("customers", "iban"): "iban",
    ("orders", "contact_phone"): "phone",
    ("orders", "refund_iban"): "iban",
}


def _columns(report):
    return {(t["name"], c["column"]): c for t in report["tables"] for c in t["columns"]}


def test_finds_pii_columns_and_nothing_else(sample_db):
    found = {key: c["pii_type"] for key, c in _columns(scan_database(sample_db)).items() if c["pii_type"]}
    assert found == EXPECTED_PII


def test_scores_and_rates_are_in_range(sample_db):
    report = scan_database(sample_db)
    assert report["summary"] == {"tables": 2, "columns": 15, "pii_columns": 7}
    for col in _columns(report).values():
        assert 0 <= col["score"] <= 100
        assert 0 <= col["empty_rate"] <= 1
        assert 0 <= col["unique_rate"] <= 1
        assert col["format_rate"] is None or 0 <= col["format_rate"] < 1


def test_scan_does_not_change_the_database(sample_db):
    before = file_hash(sample_db)
    scan_database(sample_db)
    assert file_hash(sample_db) == before


def test_readonly_connection_rejects_writes(sample_db):
    conn = connect_readonly(sample_db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM customers")
    conn.close()


def test_missing_database_is_not_created(tmp_path):
    with pytest.raises(FileNotFoundError):
        scan_database(tmp_path / "nope.db")
    assert not (tmp_path / "nope.db").exists()


def test_detects_by_values_when_column_name_says_nothing():
    values = ["10000000146", "12345678950", "10000000147", None]
    col = profile_column("t", "col_7", "TEXT", values)
    assert (col.pii_type, col.detected_by) == ("tc_no", "values")
    assert col.valid == 2


def test_detects_tc_stored_as_integer():
    col = profile_column("t", "x", "INTEGER", [10000000146, 12345678950])
    assert col.pii_type == "tc_no"
    assert col.format_rate == 1.0


def test_repeated_free_text_is_not_a_name():
    col = profile_column("t", "note", "TEXT", ["on hold", "in transit"] * 20)
    assert col.pii_type is None


def test_score_by_hand():
    # 10 rows: 2 empty, 8 non-empty, 7 valid.
    values = ["10000000146", "12345678950", "10000000214", "10000000382", "10000000450", "10000000528"]
    values += ["10000000696", "10000000147", None, " "]
    col = profile_column("t", "tc_no", "TEXT", values)
    assert col.valid == 7
    assert (col.empty_rate, col.unique_rate, col.format_rate) == (0.2, 1.0, 0.875)
    # 50 * (0.8 + 0.875) = 83.75
    assert col.score == 84


def test_repeated_values_do_not_lower_the_score():
    distinct = profile_column("t", "tc_no", "TEXT", ["10000000146", "12345678950", "10000000214", "10000000382"])
    repeated = profile_column("t", "tc_no", "TEXT", ["10000000146"] * 4)
    assert repeated.unique_rate == 0.25
    assert repeated.score == distinct.score == 100

    status = profile_column("t", "status", "TEXT", ["new", "paid"] * 10)
    assert status.unique_rate == 0.1
    assert status.score == 100


@pytest.mark.parametrize(
    "fill, fmt, expected",
    [(1, 1, 100), (0, 0, 0), (1, None, 100), (0.9, None, 90), (0.5, 0.5, 50), (1, 0, 50), (0.8, 0.6, 70)],
)
def test_quality_score(fill, fmt, expected):
    assert quality_score(fill, fmt) == expected


def test_empty_column_scores_zero():
    col = profile_column("t", "email", "TEXT", [None, "", "  "])
    assert col.score == 0
    assert col.empty_rate == 1.0


@pytest.mark.parametrize(
    "value, expected",
    [
        ("10000000147", "99999999999"),
        ("565 667", "999 999"),
        ("+90 (532) 123-45", "+99 (999) 999-99"),
        ("Ayşe İ. Öz 12", "aaaa a. aa 99"),
        ("ayse@", "aaaa@"),
        ("???", "???"),
    ],
)
def test_outline_keeps_only_the_shape(value, expected):
    assert outline(value) == expected


def test_invalid_examples_show_no_digit_or_letter_of_the_value(sample_db):
    columns = _columns(scan_database(sample_db))
    seen = 0
    for key in EXPECTED_PII:
        for example in columns[key]["invalid_examples"]:
            seen += 1
            assert all(c == "9" for c in example if c.isdigit())
            assert all(c == "a" for c in example if c.isalpha())
    assert seen > 0


def test_invalid_examples_are_distinct_shapes():
    col = profile_column("t", "phone", "TEXT", ["565 667", "512 345", "599 000", "53x"])
    assert col.invalid_examples == ["999 999", "99a"]
