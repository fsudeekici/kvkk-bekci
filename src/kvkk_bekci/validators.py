"""Validators for Turkish PII formats.

Each PII type has two checks:
- ``shape``: loose, used to decide what a column holds (e.g. "11 digits").
- ``valid``: strict, used for the format-match rate (e.g. the TC checksum).
"""

from __future__ import annotations

import re

TC = "tc_no"
IBAN = "iban"
PHONE = "phone"
EMAIL = "email"
NAME = "name"

PII_TYPES = (TC, IBAN, PHONE, EMAIL, NAME)

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_NAME_RE = re.compile(r"^[^\W\d_]+([ '.-]+[^\W\d_]+)+\.?$")
_PHONE_CHARS_RE = re.compile(r"^\+?[\d\s().-]+$")
_DATE_RE = re.compile(r"^\d{4}[-.]\d{2}[-.]\d{2}")
_IBAN_SHAPE_RE =re.compile(r"^[A-Z]{2}[0-9A-Z]{13,32}$")
_TR_IBAN_RE = re.compile(r"^TR\d{24}$")


def is_empty(value) -> bool:
    """NULL, empty string and whitespace-only all count as empty."""
    return value is None or (isinstance(value, str) and not value.strip())


def digits_of(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


# --- TC kimlik no ---------------------------------------------------------

def tc_check_digits(first9: str) -> str:
    """Return the two check digits for the first nine digits of a TC number."""
    d = [int(c) for c in first9]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = (sum(d) + d10) % 10
    return f"{d10}{d11}"


def tc_shape(value: str) -> bool:
    s = value.strip()
    return len(s) == 11 and s.isascii() and s.isdigit()


def tc_valid(value: str) -> bool:
    s = value.strip()
    return tc_shape(s) and s[0] != "0" and tc_check_digits(s[:9]) == s[9:]


# --- IBAN -----------------------------------------------------------------

def iban_compact(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def _iban_mod97(compact: str) -> int:
    rearranged = compact[4:] + compact[:4]
    # A=10 ... Z=35; digits stay as they are.
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97


def iban_check_digits(country: str, bban: str) -> str:
    """Return the two check digits that make ``country + ?? + bban`` valid."""
    return f"{98 - _iban_mod97(country + '00' + bban):02d}"


def iban_shape(value: str) -> bool:
    return bool(_IBAN_SHAPE_RE.match(iban_compact(value)))


def iban_valid(value: str) -> bool:
    """Turkish IBAN: TR + 24 digits, and the mod-97 remainder is 1."""
    compact = iban_compact(value)
    return bool(_TR_IBAN_RE.match(compact)) and _iban_mod97(compact) == 1


# --- Phone ----------------------------------------------------------------

def phone_national(value: str) -> str | None:
    """Return the 10 national digits (5XXXXXXXXX), or None if not a TR mobile."""
    s = value.strip()
    if not _PHONE_CHARS_RE.match(s):
        return None
    d = digits_of(s)
    if len(d) == 12 and d.startswith("90"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0") and not s.startswith("+"):
        d = d[1:]
    elif len(d) != 10 or s.startswith("+"):
        return None
    return d if d[0] == "5" else None


def phone_shape(value: str) -> bool:
    s = value.strip()
    if not _PHONE_CHARS_RE.match(s) or _DATE_RE.match(s):
        return False
    n = len(digits_of(s))
    # 11 bare digits is a TC number far more often than a phone.
    if n == 11 and s.isdigit() and not s.startswith("0"):
        return False
    return 10 <= n <= 13


def phone_valid(value: str) -> bool:
    return phone_national(value) is not None


# --- Email ----------------------------------------------------------------

def email_shape(value: str) -> bool:
    s = value.strip()
    return "@" in s and " " not in s


def email_valid(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


# --- Name -----------------------------------------------------------------

def name_valid(value: str) -> bool:
    """Two or more words made of letters (Turkish letters included)."""
    return bool(_NAME_RE.match(value.strip()))


SHAPE = {TC: tc_shape, IBAN: iban_shape, PHONE: phone_shape, EMAIL: email_shape, NAME: name_valid}
VALID = {TC: tc_valid, IBAN: iban_valid, PHONE: phone_valid, EMAIL: email_valid, NAME: name_valid}
