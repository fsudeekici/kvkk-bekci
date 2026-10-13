# kvkk-bekci

Find, score and mask personal data (KVKK) in a SQLite database.

## Install

```
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Use

```
kvkk-bekci seed  --db sample.db                              # sample data (Faker tr_TR)
kvkk-bekci scan  --db sample.db --out reports/               # reports/scan.json, reports/scan.html
kvkk-bekci apply --db sample.db --out masked.db              # preview only, exit code 2
kvkk-bekci apply --db sample.db --out masked.db --approve    # write the masked copy
```

`scan` and `apply` open the source database read-only. `apply` never overwrites an existing file.

## What scan finds

| Type | Strict check |
|---|---|
| `tc_no` | 11 digits, first not 0, both check digits correct |
| `iban` | `TR` + 24 digits, mod-97 remainder is 1 |
| `phone` | Turkish mobile: `+90` / `0` / bare, then `5XXXXXXXXX` |
| `email` | `local@domain.tld` |
| `name` | two or more words of letters |

A column is PII when its name says so (`tc_no`, `tckn`, `telefon`, `eposta`, `ad_soyad`, ...) or when at least 60% of its values have the loose shape of a type. The strict check then gives the format-match rate.

## Quality score

- `fill` = 1 - empty rate (NULL, `''` and whitespace count as empty)
- `format` = strictly valid values / non-empty values

PII columns: `50 * (fill + format)`. Other columns: `100 * fill`.

The unique rate (distinct values / non-empty values) is in the report for information only. It is not part of the score, because repeats are normal in columns such as city, status or a phone copied onto each order.

## Report privacy

The reports never contain raw values. Up to 3 invalid examples per PII column are shown as a shape only: every digit becomes `9`, every letter becomes `a`, punctuation and spaces stay. So `565 667` is shown as `999 999`.

## Masking

Each value is replaced using `HMAC-SHA256(salt, type + value)`, so the same input gives the same output in every row, table and run. Rows that shared a phone or IBAN before still share one after.

- Valid TC numbers and IBANs become other valid ones. IBAN spacing is kept.
- Phones keep their prefix, the leading `5` and all separators.
- Emails become `u<10 chars>@example.com`.
- Names keep their word count and letter case.
- Invalid values keep their shape (digit to digit, letter to letter) and stay invalid.
- Empty values are not changed.

Set the salt with `--salt` or `KVKK_BEKCI_SALT`.

## Limits

- **Use a secret salt on real data.** With the built-in salt anyone can mask all possible TC numbers and reverse the copy.
- Masked names come from Faker's `tr_TR` lists, so they are only stable for the same Faker version.
- A masked TC number or IBAN is valid, so it may by chance belong to a real person or account.
- Only INTEGER and TEXT values are masked. REAL and BLOB values in a PII column are left as they are.
- Masking a column with a `UNIQUE` constraint can fail on a collision; the output file is then removed.

## Tests

```
.venv/bin/pytest
```
