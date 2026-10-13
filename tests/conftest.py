import hashlib
import sqlite3

import pytest

from kvkk_bekci.seed import create_sample_db


@pytest.fixture
def sample_db(tmp_path):
    path = tmp_path / "sample.db"
    create_sample_db(path, customers=120, orders=300, seed=7)
    return path


def file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def column_values(path, table, column) -> list:
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute(f'SELECT "{column}" FROM "{table}" ORDER BY id')]
    finally:
        conn.close()
