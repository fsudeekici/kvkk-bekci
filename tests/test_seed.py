import random

import pytest

from kvkk_bekci import validators as v
from kvkk_bekci.seed import create_sample_db, make_iban, make_phone, make_tc

from conftest import column_values, file_hash


def test_generators_make_valid_values():
    rng = random.Random(1)
    for _ in range(200):
        assert v.tc_valid(make_tc(rng))
        assert v.iban_valid(make_iban(rng))
        assert v.phone_valid(make_phone(rng))


def test_row_counts(sample_db):
    assert len(column_values(sample_db, "customers", "id")) == 120
    assert len(column_values(sample_db, "orders", "id")) == 300


@pytest.mark.parametrize(
    "column, check",
    [
        ("full_name", v.name_valid),
        ("tc_no", v.tc_valid),
        ("phone", v.phone_valid),
        ("email", v.email_valid),
        ("iban", v.iban_valid),
    ],
)
def test_each_pii_column_has_good_bad_and_empty_values(sample_db, column, check):
    values = column_values(sample_db, "customers", column)
    non_empty = [x for x in values if not v.is_empty(x)]
    good = [x for x in non_empty if check(x)]

    assert len(non_empty) < len(values), "expected some empty values"
    assert len(good) < len(non_empty), "expected some bad values"
    assert len(good) > len(values) * 0.6, "most values should be good"


def test_orders_reuse_customer_pii(sample_db):
    phones = set(column_values(sample_db, "customers", "phone"))
    ibans = set(column_values(sample_db, "customers", "iban"))
    assert set(column_values(sample_db, "orders", "contact_phone")) <= phones
    assert set(column_values(sample_db, "orders", "refund_iban")) <= ibans


def test_same_seed_gives_same_db(tmp_path):
    a, b, c = tmp_path / "a.db", tmp_path / "b.db", tmp_path / "c.db"
    create_sample_db(a, 30, 50, seed=1)
    create_sample_db(b, 30, 50, seed=1)
    create_sample_db(c, 30, 50, seed=2)
    assert file_hash(a) == file_hash(b)
    assert file_hash(a) != file_hash(c)
