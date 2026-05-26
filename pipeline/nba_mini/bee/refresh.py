"""Idempotent corpus refresh: merge new roster pulls into the corpus file
without clobbering hand-curated entries.

The corpus file format (NAME|TYPE|DISPLAY, one per line, # comments) is
preserved as-is. New entries are appended in a clearly-marked section so a
human reading the file can see what came from automation vs hand-curation.

Idempotency: running refresh twice in a row is a no-op. The file is parsed
to extract existing (NAME, TYPE) keys, and only entries whose key isn't
already present get added.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from nba_mini.bee.corpus import corpus_path_for
from nba_mini.bee.roster import RosterPlayer

logger = logging.getLogger(__name__)

# Marker comment we use to delineate the auto-appended block. Re-running
# refresh keeps appending to the *end* of the file rather than mutating
# the auto-block in place — simpler, and reads clearly in git diffs.
AUTO_BLOCK_HEADER_PREFIX = "# ---- Auto-added from nba_api roster pull"


def existing_keys(corpus_text: str) -> set[tuple[str, str]]:
    """Extract the (NAME, TYPE) keys already in the corpus.

    Tolerant: skips comment/blank lines, ignores malformed rows.
    """
    keys: set[tuple[str, str]] = set()
    for line in corpus_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("|")
        if len(parts) != 3:
            continue
        name = parts[0].strip()
        type_ = parts[1].strip()
        if name and type_:
            keys.add((name, type_))
    return keys


def diff_new_entries(
    players: Iterable[RosterPlayer],
    existing: set[tuple[str, str]],
) -> list[RosterPlayer]:
    """Return players whose (last_name, "last") key isn't already in the corpus.

    Order is preserved (corresponds to the input iterable's order) and
    duplicates within the input are dropped — first occurrence wins.
    """
    seen: set[str] = set()
    out: list[RosterPlayer] = []
    for p in players:
        if p.last_name in seen:
            continue
        seen.add(p.last_name)
        if (p.last_name, "last") in existing:
            continue
        out.append(p)
    return out


def build_auto_block(
    players: list[RosterPlayer],
    *,
    today: date,
) -> str:
    """Format new players as an auto-appended block with a dated header.

    The header makes it obvious in git that the block is automation-
    generated, and the date helps a future reader audit whether a refresh
    is overdue.

    Always returns a string ending with a newline; callers can append it
    to the corpus file directly.
    """
    if not players:
        return ""
    lines: list[str] = []
    lines.append("")  # leading blank for separation from prior content
    lines.append(f"{AUTO_BLOCK_HEADER_PREFIX} ({today.isoformat()}) ----")
    for p in players:
        lines.append(f"{p.last_name}|last|{p.display}")
    return "\n".join(lines) + "\n"


def refresh_corpus(
    league: str,
    players: Iterable[RosterPlayer],
    *,
    path: Path | None = None,
    today: date | None = None,
) -> int:
    """Merge new roster pulls into the corpus file.

    Args:
        league: ``"nba"`` or ``"wnba"``; selects the corpus file.
        players: Iterable of ``RosterPlayer`` (from ``fetch_roster``).
        path: Override for the corpus file path. Defaults to the on-disk
            location.
        today: Override the date stamp on the auto-block header (used for
            tests). Defaults to the system today.

    Returns:
        The number of new entries appended (0 if everything was already
        present — refresh is idempotent).
    """
    target = path if path is not None else corpus_path_for(league)  # type: ignore[arg-type]
    if not target.exists():
        # If a fresh league file is missing, that's an error worth surfacing.
        # The hand-curated starter must exist before automation augments it.
        raise FileNotFoundError(
            f"corpus file not found at {target}; "
            "automation augments hand-curated starters, it doesn't bootstrap them"
        )

    current = target.read_text()
    existing = existing_keys(current)
    new_entries = diff_new_entries(players, existing)
    if not new_entries:
        logger.info("refresh[%s]: no new entries to append", league)
        return 0

    block = build_auto_block(new_entries, today=today or date.today())
    # Ensure the file ends with a newline before appending — otherwise
    # our leading blank merges with the prior last line.
    if current and not current.endswith("\n"):
        current = current + "\n"
    target.write_text(current + block)
    logger.info(
        "refresh[%s]: appended %d new entries to %s",
        league, len(new_entries), target,
    )
    return len(new_entries)
