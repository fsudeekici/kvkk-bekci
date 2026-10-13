"""Deterministic, format-preserving masking and the masked database copy."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
import string
from pathlib import Path

from faker.providers.person.tr_TR import Provider as _TrPerson

from .scan import ColumnResult, connect_readonly, quote_ident, scan_columns
from .validators import (
    EMAIL,
    IBAN,
    NAME,
    PHONE,
    TC,
    VALID,
    iban_check_digits,
    iban_compact,
    is_empty,
    phone_national,
    tc_check_digits,
)

DEFAULT_SALT = "kvkk-bekci-default-salt"
SALT_ENV = "KVKK_BEKCI_SALT"

_FIRST_NAMES = sorted(set(_TrPerson.first_names_male) | set(_TrPerson.first_names_female))
_LAST_NAMES = sorted(set(_TrPerson.last_names))
_BASE36 = string.ascii_lowercase + string.digits
MAX_ATTEMPTS = 100


class MaskingError(ValueError):
    """No acceptable masked value was found. The message never holds the raw value."""


class _Stream:
    """Endless deterministic numbers derived from (salt, pii_type, value)."""

    def __init__(self, salt: str, pii_type: str, key: str):
        self._key = hmac.new(salt.encode(), f"{pii_type}\0{key}".encode(), hashlib.sha256).digest()
        self._counter = 0

    def below(self, n: int) -> int:
        block = hmac.new(self._key, self._counter.to_bytes(8, "big"), hashlib.sha256).digest()
        self._counter += 1
        return int.from_bytes(block[:8], "big") % n

    def digits(self, n: int) -> str:
        return "".join(str(self.below(10)) for _ in range(n))

    def pick(self, options):
        return options[self.below(len(options))]


def _tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def _tr_lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _mask_tc(core: str, salt: str) -> str:
    stream = _Stream(salt, TC, core)
    first9 = str(1 + stream.below(9)) + stream.digits(8)
    return first9 + tc_check_digits(first9)


def _mask_iban(core: str, salt: str) -> str:
    stream = _Stream(salt, IBAN, iban_compact(core))
    bban = stream.digits(5) + "0" + stream.digits(16)
    fresh = iter("TR" + iban_check_digits("TR", bban) + bban)
    out = []
    for ch in core:
        if ch.isspace():
            out.append(ch)
        else:
            new = next(fresh)
            out.append(new.lower() if ch.islower() else new)
    return "".join(out)


def _mask_phone(core: str, salt: str) -> str:
    stream = _Stream(salt, PHONE, phone_national(core))
    # Keep the country/trunk prefix and the leading 5 of the national number.
    keep = sum(c.isdigit() for c in core) - 9
    out = []
    for ch in core:
        if not ch.isdigit():
            out.append(ch)
        elif keep > 0:
            keep -= 1
            out.append(ch)
        else:
            out.append(str(stream.below(10)))
    return "".join(out)


def _mask_email(core: str, salt: str) -> str:
    stream = _Stream(salt, EMAIL, core.lower())
    return "u" + "".join(stream.pick(_BASE36) for _ in range(10)) + "@example.com"


def _mask_name(core: str, salt: str) -> str:
    stream = _Stream(salt, NAME, " ".join(_tr_lower(core).split()))
    words = core.split()
    out = []
    for i, word in enumerate(words):
        if word.endswith(".") and i < len(words) - 1:  # title such as "Dr."
            out.append(word)
            continue
        new = stream.pick(_LAST_NAMES if i == len(words) - 1 else _FIRST_NAMES)
        if word.isupper():
            new = _tr_upper(new)
        elif word.islower():
            new = _tr_lower(new)
        out.append(new)
    # Put the original whitespace back between the words.
    pieces, rest = [], core
    for word, new in zip(words, out):
        gap, _, rest = rest.partition(word)
        pieces += [gap, new]
    return "".join(pieces)


def _mask_generic(core: str, salt: str, pii_type: str) -> str:
    """For values that fail validation: same character classes, so bad stays bad-shaped."""
    stream = _Stream(salt, pii_type, core)
    out = []
    for ch in core:
        if ch.isdigit():
            out.append(str(stream.below(10)))
        elif ch.isalpha():
            out.append(stream.pick(string.ascii_lowercase if ch.islower() else string.ascii_uppercase))
        else:
            out.append(ch)
    return "".join(out)


_MASKERS = {TC: _mask_tc, IBAN: _mask_iban, PHONE: _mask_phone, EMAIL: _mask_email, NAME: _mask_name}


def mask_value(pii_type: str, value, salt: str = DEFAULT_SALT):
    """Return the masked form of ``value``. The same input always gives the same output.

    Empty values are returned unchanged. Integers come back as integers.
    Other non-text values (REAL, BLOB) are returned unchanged.
    Raises MaskingError if no acceptable masked value is found.
    """
    if is_empty(value) or isinstance(value, bool) or not isinstance(value, (str, int)):
        return value
    if isinstance(value, int):
        return int(mask_value(pii_type, str(value), salt))

    core = value.strip()
    start = value.index(core)
    lead, trail = value[:start], value[start + len(core) :]
    if not any(c.isalnum() for c in core):
        return value
    was_valid = VALID[pii_type](core)
    # Retry with a tweaked salt in the rare case the result equals the input,
    # or an invalid value turns valid by chance (1 in 100 for a TC number).
    for attempt in range(MAX_ATTEMPTS):
        tweaked = salt if attempt == 0 else f"{salt}\0{attempt}"
        if was_valid:
            masked = _MASKERS[pii_type](core, tweaked)
        else:
            masked = _mask_generic(core, tweaked, pii_type)
        if masked != core and VALID[pii_type](masked) == was_valid:
            return lead + masked + trail
    raise MaskingError(
        f"could not mask a {'valid' if was_valid else 'invalid'} {pii_type} value "
        f"of length {len(core)} after {MAX_ATTEMPTS} attempts"
    )


def pii_columns(db_path: str | Path) -> list[ColumnResult]:
    """Columns that ``apply`` would mask."""
    conn = connect_readonly(db_path)
    try:
        return [c for c in scan_columns(conn) if c.pii_type]
    finally:
        conn.close()


def _remove_db_files(path: Path) -> None:
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def create_masked_copy(
    src_path: str | Path,
    out_path: str | Path,
    salt: str = DEFAULT_SALT,
    columns: list[ColumnResult] | None = None,
) -> list[dict]:
    """Write a masked copy of ``src_path`` to ``out_path``. The source is opened read-only.

    Returns one entry per masked column with the number of changed rows.
    """
    out_path = Path(out_path)
    if out_path.exists():
        raise FileExistsError(f"output already exists: {out_path}")
    if columns is None:
        columns = pii_columns(src_path)

    cache: dict = {}

    def sql_mask(pii_type, value):
        key = (pii_type, type(value), value)
        if key not in cache:
            cache[key] = mask_value(pii_type, value, salt)
        return cache[key]

    src = connect_readonly(src_path)
    dst = sqlite3.connect(out_path)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode = DELETE")
        dst.create_function("kvkk_mask", 2, sql_mask, deterministic=True)
        summary = []
        with dst:
            for col in columns:
                table, column = quote_ident(col.table), quote_ident(col.column)
                cursor = dst.execute(
                    f"UPDATE {table} SET {column} = kvkk_mask(?1, {column}) "
                    f"WHERE kvkk_mask(?1, {column}) IS NOT {column}",
                    (col.pii_type,),
                )
                summary.append(
                    {"table": col.table, "column": col.column, "pii_type": col.pii_type, "changed": cursor.rowcount}
                )
        # Rebuild the file so the original values do not survive in freed pages.
        dst.execute("VACUUM")
    except BaseException:
        dst.close()
        _remove_db_files(out_path)
        raise
    finally:
        src.close()
        dst.close()
    return summary
