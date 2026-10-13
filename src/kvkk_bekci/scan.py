"""Read-only scan: find PII columns and score every column."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .validators import EMAIL, IBAN, NAME, PHONE, PII_TYPES, SHAPE, TC, VALID, is_empty

SHAPE_THRESHOLD = 0.6
# A column of free text can look like names; real name columns are mostly distinct.
NAME_MIN_UNIQUE = 0.5
MAX_EXAMPLES = 3

_NAME_HINTS = {
    TC: re.compile(r"(^|_)(tc|tckn|tcno|kimlik|national_?id)(_|$)"),
    IBAN: re.compile(r"iban"),
    PHONE: re.compile(r"(^|_)(phone|telefon|tel|gsm|mobile|cep)(_|$)"),
    EMAIL: re.compile(r"e_?mail|e_?posta"),
    NAME: re.compile(
        r"(^|_)(ad|adi|soyad|soyadi|isim|surname|adsoyad)(_|$)|(full|first|last|customer|contact)_?name$|^name$"
    ),
}


@dataclass
class ColumnResult:
    table: str
    column: str
    declared_type: str
    pii_type: str | None
    detected_by: str | None  # "name", "values" or None
    rows: int
    empty: int
    distinct: int
    valid: int | None
    empty_rate: float
    unique_rate: float
    format_rate: float | None
    score: int
    invalid_examples: list[str] = field(default_factory=list)


def connect_readonly(path: str | Path) -> sqlite3.Connection:
    if not Path(path).is_file():
        raise FileNotFoundError(f"database not found: {path}")
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def outline(value: str) -> str:
    """Shape of a value (digit -> 9, letter -> a) so reports carry no raw PII."""
    return "".join("9" if c.isdigit() else "a" if c.isalpha() else c for c in value)


def quality_score(fill: float, format_rate: float | None) -> int:
    """0-100. Columns with no known format are scored on fill only."""
    if format_rate is None:
        return round(100 * fill)
    return round(50 * (fill + format_rate))


def hinted_type(column: str) -> str | None:
    lowered = column.lower()
    return next((t for t in PII_TYPES if _NAME_HINTS[t].search(lowered)), None)


def detect_type(column: str, texts: list[str], unique_rate: float) -> tuple[str | None, str | None]:
    """Return (pii_type, detected_by)."""
    hinted = hinted_type(column)
    if hinted:
        return hinted, "name"
    if not texts:
        return None, None
    rates = {t: sum(1 for s in texts if SHAPE[t](s)) / len(texts) for t in PII_TYPES}
    best = max(PII_TYPES, key=lambda t: rates[t])
    if rates[best] < SHAPE_THRESHOLD or (best == NAME and unique_rate < NAME_MIN_UNIQUE):
        return None, None
    return best, "values"


def profile_column(table: str, column: str, declared_type: str, values: list) -> ColumnResult:
    rows = len(values)
    # Integers are checked as text: a TC number is often stored as INTEGER.
    texts = [str(v) for v in values if not is_empty(v) and isinstance(v, (str, int))]
    non_empty = [v for v in values if not is_empty(v)]
    empty = rows - len(non_empty)
    distinct = len(set(non_empty))

    fill = len(non_empty) / rows if rows else 0.0
    unique = distinct / len(non_empty) if non_empty else 0.0
    pii_type, detected_by = detect_type(column, texts, unique)

    valid = format_rate = None
    examples: list[str] = []
    if pii_type:
        check = VALID[pii_type]
        valid = sum(1 for s in texts if check(s))
        format_rate = valid / len(non_empty) if non_empty else 0.0
        for s in texts:
            if not check(s) and outline(s) not in examples:
                examples.append(outline(s))
                if len(examples) == MAX_EXAMPLES:
                    break

    return ColumnResult(
        table=table,
        column=column,
        declared_type=declared_type,
        pii_type=pii_type,
        detected_by=detected_by,
        rows=rows,
        empty=empty,
        distinct=distinct,
        valid=valid,
        empty_rate=round(1 - fill, 4) if rows else 0.0,
        unique_rate=round(unique, 4),
        format_rate=None if format_rate is None else round(format_rate, 4),
        score=quality_score(fill, format_rate),
        invalid_examples=examples,
    )


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r[0] for r in rows]


def scan_columns(conn: sqlite3.Connection) -> list[ColumnResult]:
    results = []
    for table in list_tables(conn):
        for _, column, declared_type, *_ in conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall():
            values = [r[0] for r in conn.execute(f"SELECT {quote_ident(column)} FROM {quote_ident(table)}")]
            results.append(profile_column(table, column, declared_type, values))
    return results


def scan_database(path: str | Path) -> dict:
    """Scan ``path`` without writing to it and return the report as a dict."""
    conn = connect_readonly(path)
    try:
        columns = scan_columns(conn)
    finally:
        conn.close()

    tables: dict[str, dict] = {}
    for col in columns:
        entry = tables.setdefault(col.table, {"name": col.table, "rows": col.rows, "columns": []})
        entry["columns"].append({k: v for k, v in asdict(col).items() if k != "table"})

    return {
        "tool": "kvkk-bekci",
        "version": __version__,
        "database": str(path),
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "tables": len(tables),
            "columns": len(columns),
            "pii_columns": sum(1 for c in columns if c.pii_type),
        },
        "tables": list(tables.values()),
    }
