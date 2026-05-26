"""CLI entry point for refreshing the Bee names corpus.

Usage:
    uv run python -m nba_mini.bee.refresh_cli --league nba [--include-historical]

Pulls the active roster (and optionally the full historical index) from
nba_api, normalizes the last names, and appends any new entries to the
on-disk corpus file under a dated auto-block header. Idempotent — re-running
without changes is a no-op.

This script does NOT call any LLM. Pure data sourcing + normalization.
"""

from __future__ import annotations

import argparse
import logging
import sys

from nba_mini.bee.refresh import refresh_corpus
from nba_mini.bee.roster import RosterFetchError, fetch_roster

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--league",
        choices=["nba", "wnba"],
        required=True,
        help="Which league's corpus to refresh.",
    )
    parser.add_argument(
        "--include-historical",
        action="store_true",
        help=(
            "Pull the full historical player index instead of only currently-"
            "rostered players. Use sparingly; the historical index includes "
            "1980s journeyman bench players the audience won't recognize."
        ),
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

    try:
        players = fetch_roster(
            args.league,
            only_active=not args.include_historical,
        )
    except RosterFetchError as exc:
        logger.error("roster fetch failed for %s: %s", args.league, exc)
        return 1

    appended = refresh_corpus(args.league, players)
    print(f"refresh[{args.league}]: appended {appended} new entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
