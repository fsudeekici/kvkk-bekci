"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .mask import DEFAULT_SALT, SALT_ENV, create_masked_copy, pii_columns
from .report import write_reports
from .scan import scan_database
from .seed import create_sample_db

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_APPROVED = 2


def _cmd_seed(args) -> int:
    path = Path(args.db)
    if path.exists():
        if not args.force:
            print(f"error: {path} already exists (use --force to replace it)", file=sys.stderr)
            return EXIT_ERROR
        path.unlink()
    create_sample_db(path, customers=args.customers, orders=args.orders, seed=args.seed)
    print(f"Created {path}: {args.customers} customers, {args.orders} orders (seed {args.seed})")
    return EXIT_OK


def _cmd_scan(args) -> int:
    report = scan_database(args.db)
    for table in report["tables"]:
        print(f"{table['name']} ({table['rows']} rows)")
        for col in table["columns"]:
            print(f"  {col['column']:<16} {col['pii_type'] or '-':<8} score {col['score']:>3}")
    json_path, html_path = write_reports(report, args.out)
    print(f"\n{report['summary']['pii_columns']} PII columns in {report['summary']['columns']} columns")
    print(f"Reports: {json_path}, {html_path}")
    return EXIT_OK


def _cmd_apply(args) -> int:
    columns = pii_columns(args.db)
    if not columns:
        print("No PII columns found; nothing to mask.")
        return EXIT_OK

    if not args.approve:
        print(f"Would write a masked copy of {args.db} to {args.out}, masking:")
        for col in columns:
            print(f"  {col.table}.{col.column} ({col.pii_type}, {col.rows - col.empty} values)")
        print("\nNothing was written. Run again with --approve to create the copy.")
        return EXIT_NOT_APPROVED

    salt = args.salt or os.environ.get(SALT_ENV) or DEFAULT_SALT
    if salt == DEFAULT_SALT:
        print(
            f"warning: using the built-in salt; masked values can be guessed back. "
            f"Set --salt or {SALT_ENV} for real data.",
            file=sys.stderr,
        )
    summary = create_masked_copy(args.db, args.out, salt=salt, columns=columns)
    for item in summary:
        print(f"  {item['table']}.{item['column']} ({item['pii_type']}): {item['changed']} rows masked")
    print(f"Masked copy written to {args.out}. {args.db} was not changed.")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kvkk-bekci", description="Find, score and mask personal data in SQLite.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="create a sample database with fake Turkish customers and orders")
    seed.add_argument("--db", default="sample.db", help="path of the database to create (default: sample.db)")
    seed.add_argument("--customers", type=int, default=200)
    seed.add_argument("--orders", type=int, default=500)
    seed.add_argument("--seed", type=int, default=42, help="random seed; the same seed gives the same data")
    seed.add_argument("--force", action="store_true", help="replace the database if it exists")
    seed.set_defaults(func=_cmd_seed)

    scan = sub.add_parser("scan", help="find PII columns and write HTML and JSON reports (read-only)")
    scan.add_argument("--db", required=True, help="database to scan")
    scan.add_argument("--out", default="reports", help="report directory (default: reports)")
    scan.set_defaults(func=_cmd_scan)

    apply = sub.add_parser("apply", help="write a masked copy of the database")
    apply.add_argument("--db", required=True, help="source database (never modified)")
    apply.add_argument("--out", required=True, help="path of the masked copy to create")
    apply.add_argument("--approve", action="store_true", help="actually write the copy; without it only a preview")
    apply.add_argument("--salt", help=f"secret for masking (default: ${SALT_ENV}, then a built-in value)")
    apply.set_defaults(func=_cmd_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, FileExistsError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
