"""Build a sample SQLite database with Turkish customers and orders."""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

from .validators import iban_check_digits, tc_check_digits

BAD_RATE = 0.10
EMPTY_RATE = 0.08

CITIES = ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana", "Konya", "Gaziantep", "Kayseri", "Trabzon"]
STATUSES = ["new", "paid", "shipped", "delivered", "cancelled"]
EMPTY_VALUES = [None, "", "  "]
_BASE_DATE = date(2024, 1, 1)

SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    full_name TEXT,
    tc_no TEXT,
    phone TEXT,
    email TEXT,
    iban TEXT,
    city TEXT,
    created_at TEXT
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date TEXT,
    amount REAL,
    status TEXT,
    contact_phone TEXT,
    refund_iban TEXT
);
"""


def _digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def make_tc(rng: random.Random) -> str:
    first9 = rng.choice("123456789") + _digits(rng, 8)
    return first9 + tc_check_digits(first9)


def make_iban(rng: random.Random) -> str:
    # Turkish BBAN: 5-digit bank code, one reserved 0, 16-digit account number.
    bban = _digits(rng, 5) + "0" + _digits(rng, 16)
    iban = "TR" + iban_check_digits("TR", bban) + bban
    if rng.random() < 0.5:
        iban = " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))
    return iban


def make_phone(rng: random.Random) -> str:
    a, b, c, d = "5" + _digits(rng, 2), _digits(rng, 3), _digits(rng, 2), _digits(rng, 2)
    return rng.choice(
        [f"+90 {a} {b} {c} {d}", f"0{a} {b} {c} {d}", f"0{a}{b}{c}{d}", f"+90 ({a}) {b}-{c}-{d}", f"{a}{b}{c}{d}"]
    )


def _bad_tc(rng: random.Random) -> str:
    tc = make_tc(rng)
    wrong_last = str((int(tc[-1]) + rng.randint(1, 9)) % 10)
    return rng.choice([tc[:-1] + wrong_last, tc[:-1], tc[:5] + "X" + tc[6:]])


def _bad_iban(rng: random.Random) -> str:
    iban = make_iban(rng).replace(" ", "")
    wrong_check = f"{(int(iban[2:4]) + rng.randint(1, 90)) % 97:02d}"
    if wrong_check == iban[2:4]:
        wrong_check = f"{(int(wrong_check) + 1) % 97:02d}"
    return rng.choice([iban[:2] + wrong_check + iban[4:], iban[:-3]])


def _bad_phone(rng: random.Random) -> str:
    return rng.choice([f"5{_digits(rng, 2)} {_digits(rng, 3)}", f"0212 {_digits(rng, 3)} {_digits(rng, 4)}", "yok"])


def _bad_email(email: str, rng: random.Random) -> str:
    local, _, domain = email.partition("@")
    return rng.choice([local + domain, local + "@", f"{local} @{domain}"])


def _bad_name(name: str, rng: random.Random) -> str:
    return rng.choice([name.split()[0], name + " 123", "???"])


def _dirty(rng: random.Random, good, bad):
    """Return an empty, a bad or the good value."""
    roll = rng.random()
    if roll < EMPTY_RATE:
        return rng.choice(EMPTY_VALUES)
    if roll < EMPTY_RATE + BAD_RATE:
        return bad()
    return good


def create_sample_db(path: str | Path, customers: int = 200, orders: int = 500, seed: int = 42) -> None:
    """Create the sample database at ``path``. The same seed gives the same data."""
    rng = random.Random(seed)
    fake = Faker("tr_TR")
    fake.seed_instance(seed)

    customer_rows = []
    for cid in range(1, customers + 1):
        name, email = fake.name(), fake.email()
        customer_rows.append(
            (
                cid,
                _dirty(rng, name, lambda: _bad_name(name, rng)),
                _dirty(rng, make_tc(rng), lambda: _bad_tc(rng)),
                _dirty(rng, make_phone(rng), lambda: _bad_phone(rng)),
                _dirty(rng, email, lambda: _bad_email(email, rng)),
                _dirty(rng, make_iban(rng), lambda: _bad_iban(rng)),
                rng.choice(CITIES),
                (_BASE_DATE + timedelta(days=rng.randint(0, 364))).isoformat(),
            )
        )

    order_rows = []
    for oid in range(1, orders + 1):
        customer = rng.choice(customer_rows)
        order_rows.append(
            (
                oid,
                customer[0],
                (_BASE_DATE + timedelta(days=rng.randint(365, 729))).isoformat(),
                round(rng.uniform(50, 5000), 2),
                rng.choice(STATUSES),
                customer[3],
                customer[5],
            )
        )

    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.executescript(SCHEMA)
            conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?)", customer_rows)
            conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", order_rows)
    finally:
        conn.close()
