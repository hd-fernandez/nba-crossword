"""Tests for the daily Bee generation CLI (`nba_mini.bee.generate_cli`).

These exercise the file-writing / idempotency / numbering wrapper around
`generate_bee`. They use the real packaged corpus (no network, no LLM) and a
tmp output dir so nothing touches the repo's puzzles/.
"""

from __future__ import annotations

import json
from pathlib import Path

from nba_mini.bee.generate_cli import (
    bee_path_for,
    main,
    next_bee_number,
)
from nba_mini.bee.schema import BeePuzzle


def test_main_writes_bee_into_league_bee_subdir(tmp_path: Path) -> None:
    rc = main(["--league", "nba", "--date", "2026-06-01", "--out", str(tmp_path)])
    assert rc == 0
    # The <league>/bee subdirs are always appended under --out.
    written = bee_path_for("2026-06-01", tmp_path / "nba" / "bee")
    assert written.exists()
    payload = json.loads(written.read_text())
    assert payload["date"] == "2026-06-01"
    assert payload["league"] == "nba"
    # Round-trips the schema.
    parsed = BeePuzzle.model_validate(payload)
    assert parsed.bee_number >= 1
    assert "\n" in written.read_text()  # pretty-printed


def test_main_is_deterministic_for_a_date(tmp_path: Path) -> None:
    main(["--league", "nba", "--date", "2026-06-01", "--out", str(tmp_path)])
    first = bee_path_for("2026-06-01", tmp_path / "nba" / "bee").read_text()
    # Regenerate to a different dir; same date => identical board (seed is the
    # date ordinal). Compare the puzzle content, ignoring generated_at.
    other = tmp_path / "again"
    main(["--league", "nba", "--date", "2026-06-01", "--out", str(other), "--force"])
    second = bee_path_for("2026-06-01", other / "nba" / "bee").read_text()
    a = json.loads(first)
    b = json.loads(second)
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b


def test_main_idempotent_when_file_exists(tmp_path: Path) -> None:
    rc1 = main(["--league", "nba", "--date", "2026-06-01", "--out", str(tmp_path)])
    assert rc1 == 0
    written = bee_path_for("2026-06-01", tmp_path / "nba" / "bee")
    first_mtime = written.stat().st_mtime_ns

    # Second run, no --force: must be a no-op (file untouched).
    rc2 = main(["--league", "nba", "--date", "2026-06-01", "--out", str(tmp_path)])
    assert rc2 == 0
    assert written.stat().st_mtime_ns == first_mtime


def test_main_dry_run_writes_no_file(tmp_path: Path, capsys) -> None:
    rc = main(
        ["--league", "wnba", "--date", "2026-06-01", "--out", str(tmp_path), "--dry-run"]
    )
    assert rc == 0
    assert not bee_path_for("2026-06-01", tmp_path / "wnba" / "bee").exists()
    # Dry-run prints valid JSON to stdout.
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["league"] == "wnba"


def test_main_invalid_date_exits(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(SystemExit):
        main(["--league", "nba", "--date", "nope", "--out", str(tmp_path)])


def test_next_bee_number_counts_dated_files(tmp_path: Path) -> None:
    bee_dir = tmp_path / "nba" / "bee"
    bee_dir.mkdir(parents=True)
    # No files yet => #1.
    assert next_bee_number(bee_dir, "2026-06-01") == 1
    (bee_dir / "2026-05-20.json").write_text("{}")
    (bee_dir / "2026-05-25.json").write_text("{}")
    (bee_dir / "example.json").write_text("{}")  # excluded
    # Two earlier dated files => target is #3.
    assert next_bee_number(bee_dir, "2026-06-01") == 3
    # A backfill between them counts only the strictly-earlier one.
    assert next_bee_number(bee_dir, "2026-05-22") == 2
