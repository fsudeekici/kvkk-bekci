"""Write the scan result as JSON and as a self-contained HTML page."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

_CSS = """
:root { --bg:#fff; --fg:#1c2330; --muted:#5d6878; --line:#dfe3ea; --head:#f4f6f9;
        --good:#1a7f4b; --mid:#a86400; --bad:#c0362c; --tag:#e6eefc; --tagfg:#1d4fb8; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14181f; --fg:#e4e8ef; --muted:#98a3b3; --line:#2b323d; --head:#1b212a;
          --good:#4fc98a; --mid:#e3a64a; --bad:#f0776c; --tag:#1d2c4a; --tagfg:#9dbcff; }
}
body { margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
       font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width:1100px; margin:0 auto; }
h1 { font-size:22px; margin:0 0 4px; }
h2 { font-size:17px; margin:32px 0 8px; }
.meta, .note { color:var(--muted); font-size:13px; }
.cards { display:flex; flex-wrap:wrap; gap:12px; margin:16px 0; }
.card { border:1px solid var(--line); border-radius:8px; padding:10px 16px; min-width:110px; }
.card b { display:block; font-size:22px; }
.wrap { overflow-x:auto; border:1px solid var(--line); border-radius:8px; }
table { border-collapse:collapse; width:100%; font-size:14px; }
th, td { padding:7px 10px; text-align:left; border-bottom:1px solid var(--line); white-space:nowrap; }
tr:last-child td { border-bottom:0; }
th { background:var(--head); font-weight:600; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
.tag { background:var(--tag); color:var(--tagfg); border-radius:4px; padding:1px 7px; font-size:12px; }
.score { font-weight:700; }
.good { color:var(--good); } .mid { color:var(--mid); } .bad { color:var(--bad); }
.chips { display:flex; flex-wrap:wrap; gap:6px; }
.chip { font:12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space:pre;
        border:1px solid var(--line); border-radius:4px; background:var(--head); padding:1px 6px; }
.chip .sp { color:var(--muted); }
"""


def write_json(report: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pct(rate: float | None) -> str:
    return "–" if rate is None else f"{rate * 100:.1f}%"


def _band(score: int) -> str:
    return "good" if score >= 85 else "mid" if score >= 60 else "bad"


def _chip(example: str) -> str:
    """One boxed example. Spaces are drawn as a muted ␣ so they stay visible."""
    text = escape(example).replace(" ", '<span class="sp">␣</span>')
    return f'<code class="chip">{text}</code>'


def _column_row(col: dict) -> str:
    pii = f'<span class="tag">{escape(col["pii_type"])}</span>' if col["pii_type"] else "–"
    chips = "".join(_chip(e) for e in col["invalid_examples"])
    examples = f'<div class="chips">{chips}</div>' if chips else "–"
    return (
        "<tr>"
        f"<td>{escape(col['column'])}</td>"
        f"<td>{escape(col['declared_type'] or '–')}</td>"
        f"<td>{pii}</td>"
        f"<td class='num'>{_pct(col['empty_rate'])}</td>"
        f"<td class='num'>{_pct(col['unique_rate'])}</td>"
        f"<td class='num'>{_pct(col['format_rate'])}</td>"
        f"<td class='num score {_band(col['score'])}'>{col['score']}</td>"
        f"<td>{examples}</td>"
        "</tr>"
    )


def _table_section(table: dict) -> str:
    rows = "\n".join(_column_row(c) for c in table["columns"])
    return f"""<h2>{escape(table['name'])} <span class="meta">({table['rows']} rows)</span></h2>
<div class="wrap"><table>
<thead><tr><th>Column</th><th>Type</th><th>PII</th><th class="num">Empty</th><th class="num">Unique</th>
<th class="num">Format match</th><th class="num">Score</th><th>Invalid examples</th></tr></thead>
<tbody>
{rows}
</tbody></table></div>"""


def render_html(report: dict) -> str:
    summary = report["summary"]
    sections = "\n".join(_table_section(t) for t in report["tables"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>kvkk-bekci scan report</title>
<style>{_CSS}</style>
</head>
<body><main>
<h1>kvkk-bekci scan report</h1>
<div class="meta">{escape(report['database'])} · scanned {escape(report['scanned_at'])} · v{escape(report['version'])}</div>
<div class="cards">
<div class="card"><b>{summary['tables']}</b>tables</div>
<div class="card"><b>{summary['columns']}</b>columns</div>
<div class="card"><b>{summary['pii_columns']}</b>PII columns</div>
</div>
<p class="note">Score = 50% filled + 50% format match for PII columns; filled rate for the rest.
Unique is shown for information only. Invalid examples show the shape only (9 = digit, a = letter, ␣ = space).</p>
{sections}
</main></body>
</html>
"""


def write_html(report: dict, path: str | Path) -> None:
    Path(path).write_text(render_html(report), encoding="utf-8")


def write_reports(report: dict, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path, html_path = out / "scan.json", out / "scan.html"
    write_json(report, json_path)
    write_html(report, html_path)
    return json_path, html_path
