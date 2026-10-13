import re
import sqlite3

import pytest

from kvkk_bekci import validators as v
from kvkk_bekci import mask
from kvkk_bekci.mask import MaskingError, create_masked_copy, mask_value
from kvkk_bekci.scan import scan_database

from conftest import column_values, file_hash

PII = [
    ("customers", "full_name", "name"),
    ("customers", "tc_no", "tc_no"),
    ("customers", "phone", "phone"),
    ("customers", "email", "email"),
    ("customers", "iban", "iban"),
    ("orders", "contact_phone", "phone"),
    ("orders", "refund_iban", "iban"),
]


def shape(value: str) -> str:
    """Character-class outline: digits -> 9, letters -> a, the rest kept."""
    return re.sub(r"[^\W\d_]", "a", re.sub(r"\d", "9", value))


@pytest.fixture
def masked_db(sample_db, tmp_path):
    out = tmp_path / "masked.db"
    create_masked_copy(sample_db, out, salt="test-salt")
    return out


# --- single values --------------------------------------------------------

@pytest.mark.parametrize(
    "pii_type, value",
    [
        ("tc_no", "10000000146"),
        ("iban", "TR33 0006 1005 1978 6457 8413 26"),
        ("phone", "+90 (532) 123-45-67"),
        ("email", "ayse@firma.com.tr"),
        ("name", "Ayşe Yılmaz"),
        ("tc_no", "1000000014X"),
    ],
)
def test_same_input_same_output(pii_type, value):
    first = mask_value(pii_type, value, "s")
    assert first == mask_value(pii_type, value, "s")
    assert first != value
    assert first != mask_value(pii_type, value, "other-salt")


def test_tc_stays_valid():
    masked = mask_value("tc_no", "10000000146")
    assert v.tc_valid(masked)


@pytest.mark.parametrize("iban", ["TR330006100519786457841326", "TR33 0006 1005 1978 6457 8413 26"])
def test_iban_stays_valid_and_keeps_spacing(iban):
    masked = mask_value("iban", iban)
    assert v.iban_valid(masked)
    assert shape(masked) == shape(iban)


def test_iban_spacing_does_not_change_the_result():
    plain = mask_value("iban", "TR330006100519786457841326")
    spaced = mask_value("iban", "TR33 0006 1005 1978 6457 8413 26")
    assert spaced.replace(" ", "") == plain


@pytest.mark.parametrize("phone", ["+90 532 123 45 67", "0532 123 45 67", "5321234567", "+90 (532) 123-45-67"])
def test_phone_keeps_format_and_prefix(phone):
    masked = mask_value("phone", phone)
    assert v.phone_valid(masked)
    assert shape(masked) == shape(phone)
    assert masked[: phone.index("5") + 1] == phone[: phone.index("5") + 1]


def test_phone_format_does_not_change_the_number():
    a = mask_value("phone", "+90 532 123 45 67")
    b = mask_value("phone", "05321234567")
    assert v.phone_national(a) == v.phone_national(b)


def test_email_stays_valid_and_hides_domain():
    masked = mask_value("email", "ayse@firma.com.tr")
    assert v.email_valid(masked)
    assert "ayse" not in masked and "firma" not in masked


@pytest.mark.parametrize("name", ["Ayşe Yılmaz", "AYŞE YILMAZ", "Dr. Ali Veli Öztürk", "ali  veli"])
def test_name_keeps_word_count_and_case(name):
    masked = mask_value("name", name)
    assert v.name_valid(masked)
    assert len(masked.split()) == len(name.split())
    for old, new in zip(name.split(), masked.split()):
        assert old.isupper() == new.isupper()
        assert old.islower() == new.islower()


def test_name_keeps_title():
    assert mask_value("name", "Dr. Ali Veli").startswith("Dr. ")


@pytest.mark.parametrize(
    "pii_type, value, check",
    [
        ("tc_no", "10000000147", v.tc_shape),
        ("tc_no", "1000000014X", None),
        ("iban", "TR340006100519786457841326", None),
        ("phone", "532 123", None),
        ("email", "ayse.example.com", None),
    ],
)
def test_invalid_values_keep_their_shape(pii_type, value, check):
    masked = mask_value(pii_type, value)
    assert masked != value
    assert shape(masked) == shape(value)
    if check:
        assert check(masked)


def test_invalid_tc_never_becomes_valid():
    for i in range(2000):
        bad = f"{100000000 + i}00"
        if not v.tc_valid(bad):
            assert not v.tc_valid(mask_value("tc_no", bad))


@pytest.mark.parametrize("value", [None, "", "   ", "???"])
def test_empty_values_are_unchanged(value):
    assert mask_value("tc_no", value) == value


def test_integer_stays_integer():
    masked = mask_value("tc_no", 10000000146)
    assert isinstance(masked, int)
    assert v.tc_valid(str(masked))
    assert str(masked) == mask_value("tc_no", "10000000146")


def test_surrounding_whitespace_is_kept():
    assert mask_value("tc_no", " 10000000146 ") == f" {mask_value('tc_no', '10000000146')} "


def test_raises_when_no_masked_value_is_found(monkeypatch):
    # A masker that always hands back its input can never succeed.
    monkeypatch.setitem(mask._MASKERS, "tc_no", lambda core, salt: core)
    with pytest.raises(MaskingError) as excinfo:
        mask_value("tc_no", "10000000146")
    assert "100 attempts" in str(excinfo.value)
    assert "10000000146" not in str(excinfo.value)


def test_raises_when_invalid_value_keeps_turning_valid(monkeypatch):
    monkeypatch.setattr(mask, "_mask_generic", lambda core, salt, pii_type: "10000000146")
    with pytest.raises(MaskingError):
        mask_value("tc_no", "10000000147")


def test_masking_error_stops_the_copy_and_leaves_no_output(sample_db, tmp_path, monkeypatch):
    monkeypatch.setitem(mask._MASKERS, "tc_no", lambda core, salt: core)
    out = tmp_path / "out.db"
    with pytest.raises(sqlite3.Error):
        create_masked_copy(sample_db, out)
    assert not out.exists()


# --- whole database -------------------------------------------------------

def test_source_is_not_changed(sample_db, tmp_path):
    before = file_hash(sample_db)
    create_masked_copy(sample_db, tmp_path / "masked.db")
    assert file_hash(sample_db) == before


def test_two_runs_give_the_same_data(sample_db, masked_db, tmp_path):
    again = tmp_path / "again.db"
    create_masked_copy(sample_db, again, salt="test-salt")
    for table, column, _ in PII:
        assert column_values(masked_db, table, column) == column_values(again, table, column)


def test_every_pii_value_is_replaced_with_the_same_shape(sample_db, masked_db):
    for table, column, pii_type in PII:
        before = column_values(sample_db, table, column)
        after = column_values(masked_db, table, column)
        assert len(before) == len(after)
        for old, new in zip(before, after):
            if v.is_empty(old) or not any(c.isalnum() for c in old):
                assert new == old
                continue
            assert new != old
            assert v.VALID[pii_type](new) == v.VALID[pii_type](old)
            if pii_type in ("tc_no", "iban", "phone"):
                assert shape(new) == shape(old)


def test_other_columns_are_untouched(sample_db, masked_db):
    for table, column in [("customers", "id"), ("customers", "city"), ("orders", "amount"), ("orders", "customer_id")]:
        assert column_values(masked_db, table, column) == column_values(sample_db, table, column)


def test_orders_still_match_their_customer(masked_db):
    conn = sqlite3.connect(masked_db)
    rows = conn.execute(
        "SELECT o.contact_phone, c.phone, o.refund_iban, c.iban FROM orders o JOIN customers c ON c.id = o.customer_id"
    ).fetchall()
    conn.close()
    assert len(rows) == 300
    for contact_phone, phone, refund_iban, iban in rows:
        assert contact_phone == phone
        assert refund_iban == iban


def test_original_values_are_not_left_in_the_file(sample_db, masked_db):
    raw = masked_db.read_bytes()
    for column in ("tc_no", "email", "iban"):
        for value in column_values(sample_db, "customers", column):
            if not v.is_empty(value):
                assert value.encode() not in raw


def test_masked_copy_scans_like_the_original(sample_db, masked_db):
    def rates(path):
        return {
            (t["name"], c["column"]): (c["pii_type"], c["empty_rate"], c["format_rate"])
            for t in scan_database(path)["tables"]
            for c in t["columns"]
        }

    assert rates(masked_db) == rates(sample_db)


def test_refuses_to_overwrite(sample_db, masked_db):
    before = file_hash(masked_db)
    with pytest.raises(FileExistsError):
        create_masked_copy(sample_db, masked_db)
    assert file_hash(masked_db) == before


def test_failed_run_leaves_no_output(tmp_path):
    src = tmp_path / "src.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, tc_no TEXT)")
    conn.execute("INSERT INTO t VALUES (1, '10000000146')")
    # Reject any change to tc_no so the masking UPDATE fails.
    conn.execute("CREATE TRIGGER no_update BEFORE UPDATE ON t BEGIN SELECT RAISE(ABORT, 'locked'); END")
    conn.commit()
    conn.close()

    out = tmp_path / "out.db"
    with pytest.raises(sqlite3.Error):
        create_masked_copy(src, out)
    assert not out.exists()
