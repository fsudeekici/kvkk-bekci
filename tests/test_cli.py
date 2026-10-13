import json

from kvkk_bekci.cli import EXIT_ERROR, EXIT_NOT_APPROVED, EXIT_OK, main

from conftest import column_values, file_hash


def test_seed_creates_db_and_refuses_to_replace(tmp_path, capsys):
    db = tmp_path / "s.db"
    args = ["seed", "--db", str(db), "--customers", "20", "--orders", "30"]
    assert main(args) == EXIT_OK
    before = file_hash(db)

    assert main(args) == EXIT_ERROR
    assert "already exists" in capsys.readouterr().err
    assert file_hash(db) == before

    assert main(args + ["--force", "--seed", "9"]) == EXIT_OK
    assert file_hash(db) != before


def test_scan_writes_reports_and_leaves_db_alone(sample_db, tmp_path, capsys):
    before = file_hash(sample_db)
    out = tmp_path / "reports"

    assert main(["scan", "--db", str(sample_db), "--out", str(out)]) == EXIT_OK

    assert file_hash(sample_db) == before
    assert json.loads((out / "scan.json").read_text(encoding="utf-8"))["summary"]["pii_columns"] == 7
    assert (out / "scan.html").is_file()
    assert "7 PII columns" in capsys.readouterr().out


def test_scan_missing_db(tmp_path, capsys):
    assert main(["scan", "--db", str(tmp_path / "nope.db"), "--out", str(tmp_path / "r")]) == EXIT_ERROR
    assert "not found" in capsys.readouterr().err
    assert not (tmp_path / "r").exists()


def test_apply_without_approve_writes_nothing(sample_db, tmp_path, capsys):
    out = tmp_path / "masked.db"

    assert main(["apply", "--db", str(sample_db), "--out", str(out)]) == EXIT_NOT_APPROVED

    assert not out.exists()
    printed = capsys.readouterr().out
    assert "customers.tc_no" in printed and "--approve" in printed


def test_apply_with_approve_writes_masked_copy(sample_db, tmp_path, capsys):
    out = tmp_path / "masked.db"
    before = file_hash(sample_db)

    assert main(["apply", "--db", str(sample_db), "--out", str(out), "--approve", "--salt", "s3cret"]) == EXIT_OK

    assert file_hash(sample_db) == before
    assert column_values(out, "customers", "tc_no") != column_values(sample_db, "customers", "tc_no")
    assert "warning" not in capsys.readouterr().err


def test_apply_warns_about_default_salt_and_reads_env(sample_db, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("KVKK_BEKCI_SALT", raising=False)
    assert main(["apply", "--db", str(sample_db), "--out", str(tmp_path / "a.db"), "--approve"]) == EXIT_OK
    assert "warning" in capsys.readouterr().err

    monkeypatch.setenv("KVKK_BEKCI_SALT", "from-env")
    assert main(["apply", "--db", str(sample_db), "--out", str(tmp_path / "b.db"), "--approve"]) == EXIT_OK
    assert "warning" not in capsys.readouterr().err
    assert column_values(tmp_path / "a.db", "customers", "tc_no") != column_values(tmp_path / "b.db", "customers", "tc_no")


def test_apply_refuses_existing_output(sample_db, tmp_path, capsys):
    out = tmp_path / "masked.db"
    out.write_text("keep me")

    assert main(["apply", "--db", str(sample_db), "--out", str(out), "--approve"]) == EXIT_ERROR

    assert out.read_text() == "keep me"
    assert "already exists" in capsys.readouterr().err
