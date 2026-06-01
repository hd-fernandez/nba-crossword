"""CLI entry point for generating the daily Spelling Bee puzzle.

Usage:
    uv run python -m nba_mini.bee.generate_cli --league nba [--date YYYY-MM-DD] \
        [--out ../puzzles] [--force] [--dry-run]

Unlike the crossword, the Bee is corpus-driven, not news-driven: it needs no
games and no LLM. It picks a deterministic board from the league's names
corpus using the date ordinal as the seed, so the same date always yields the
same Bee. Output lands in ``<out>/<league>/bee/<date>.json`` (the league + bee
subdirs are always appended under ``--out``), mirroring the crossword's
per-league layout and what the frontend serves.

Idempotent: if the file already exists and ``--force`` isn't passed, the run
exits clean without touching it — safe for the daily cron to re-run.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date as date_cls
from pathlib import Path

from nba_mini.bee.corpus import League
from nba_mini.bee.generate import BeeGenerationError, generate_bee
from nba_mini.bee.schema import BeePuzzle
from nba_mini.generate import today_in_eastern

logger = logging.getLogger(__name__)

_DATED_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def bee_path_for(date_str: str, bee_dir: Path) -> Path:
    """Return the JSON file path for a given date inside ``bee_dir``."""
    return bee_dir / f"{date_str}.json"


def next_bee_number(bee_dir: Path, target_iso: str) -> int:
    """Sequential Bee number for ``target_iso``: count of dated Bee files at or
    before the target date, plus 1.

    Mirrors the crossword's ``next_puzzle_number`` so re-runs and backfills get
    a stable number. ``example.json`` is excluded — it isn't a published Bee.
    """
    if not bee_dir.exists():
        return 1
    earlier_or_equal = 0
    for p in bee_dir.iterdir():
        if not _DATED_FILENAME_RE.match(p.name):
            continue
        if p.stem == target_iso:
            continue
        if p.stem < target_iso:
            earlier_or_equal += 1
    return earlier_or_equal + 1


def write_bee_json(puzzle: BeePuzzle, path: Path) -> None:
    """Serialize a ``BeePuzzle`` to ``path`` as pretty-printed UTF-8 JSON.

    Same round-trip-through-``model_dump_json`` approach as the crossword
    writer so datetime / enum serialization matches pydantic's canonical form.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(puzzle.model_dump_json())
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _resolve_date(arg: str | None) -> date_cls:
    if arg is None:
        return today_in_eastern()
    try:
        return date_cls.fromisoformat(arg)
    except ValueError as exc:
        raise SystemExit(f"invalid --date {arg!r}: expected YYYY-MM-DD ({exc})") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m nba_mini.bee.generate_cli",
        description="Generate the daily NBA/WNBA Spelling Bee for a given date.",
    )
    parser.add_argument(
        "--league",
        choices=["nba", "wnba"],
        required=True,
        help="Which league's corpus to draw from.",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Publish date (ISO YYYY-MM-DD). Defaults to today in US/Eastern.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help=(
            "Root output directory. Defaults to puzzles/. The <league>/bee "
            "subdirs are always appended, so the Bee lands in "
            "<out>/<league>/bee/<date>.json."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing Bee file at the target path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip writing the file; print the Bee JSON to stdout.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    league: League = args.league
    target_date = _resolve_date(args.date)
    iso = target_date.isoformat()
    out_root = Path(args.out) if args.out else Path("puzzles")
    bee_dir = out_root / league / "bee"
    target_path = bee_path_for(iso, bee_dir)

    # Idempotency: existing file + no --force = no-op. Safe for cron re-runs.
    if target_path.exists() and not args.force and not args.dry_run:
        logger.info(
            "bee for %s already exists at %s; pass --force to regenerate",
            iso,
            target_path,
        )
        return 0

    # Daily seed: date ordinal, same convention as the crossword. Deterministic
    # per date, varies day to day.
    seed = target_date.toordinal()
    bee_number = next_bee_number(bee_dir, iso)

    try:
        puzzle = generate_bee(
            league, date_str=iso, bee_number=bee_number, seed=seed
        )
    except BeeGenerationError as exc:
        logger.error("bee generation failed for %s %s: %s", league, iso, exc)
        return 1

    logger.info(
        "bee[%s] %s: center=%s outer=%s valid=%d pangrams=%d",
        league,
        iso,
        puzzle.center_letter,
        "".join(puzzle.outer_letters),
        len(puzzle.valid_names),
        len(puzzle.pangrams),
    )

    if args.dry_run:
        payload = json.loads(puzzle.model_dump_json())
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0

    write_bee_json(puzzle, target_path)
    logger.info("wrote bee to %s", target_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
