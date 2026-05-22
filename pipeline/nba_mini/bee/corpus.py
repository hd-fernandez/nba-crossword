"""Loader for the per-league hoops Spelling Bee names corpus.

The corpus files at ``pipeline/data/bee/names_<league>.txt`` are
hand-curated for v3 launch. Each line is ``NAME|TYPE|DISPLAY``, with
``#`` lines and blank lines ignored. The loader is tolerant: malformed
rows are dropped with a logged warning rather than raising, so a stray
edit doesn't brick the daily Bee.

Length rule: only names of 4–10 letters are kept (Bee mechanic minimum
is 4; we cap at 10 for practical board fit, though longer names are
fine in the corpus — they just can't appear in any puzzle).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

League = Literal["nba", "wnba"]
EntryType = Literal["last", "first_mononym", "nickname"]

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "bee"

MIN_NAME_LEN = 4
MAX_NAME_LEN = 10
NAME_PATTERN = re.compile(r"^[A-Z]+$")
VALID_TYPES = {"last", "first_mononym", "nickname"}


class CorpusNotFoundError(FileNotFoundError):
    """Raised when the corpus file for a league is missing."""


@dataclass(frozen=True)
class CorpusEntry:
    """A single name in the corpus.

    Attributes:
        name: Uppercase A–Z, used for matching against the Bee board.
        type: One of ``last``, ``first_mononym``, ``nickname``.
        display: Original casing + punctuation for the found-names list.
    """

    name: str
    type: EntryType
    display: str


def corpus_path_for(league: League) -> Path:
    """Resolve the corpus file path for a league."""
    return DATA_DIR / f"names_{league}.txt"


def load_corpus(
    league: League,
    *,
    path: Path | None = None,
    min_length: int = MIN_NAME_LEN,
    max_length: int = MAX_NAME_LEN,
) -> list[CorpusEntry]:
    """Load and validate the corpus for ``league``.

    Args:
        league: ``"nba"`` or ``"wnba"``.
        path: Optional override for the corpus file path. Defaults to
            ``pipeline/data/bee/names_<league>.txt``.
        min_length: Drop names shorter than this. Default 4 (Bee minimum).
        max_length: Drop names longer than this. Default 10.

    Returns:
        Deduped list of ``CorpusEntry`` (de-dup is on the (name, type)
        pair — the same surface name can appear twice in the file with
        different types, e.g., ``LEBRON`` as ``first_mononym`` AND
        ``last`` for separate display rows; we keep the first).

    Raises:
        CorpusNotFoundError: if the corpus file is missing.
    """
    target = path if path is not None else corpus_path_for(league)
    if not target.exists():
        raise CorpusNotFoundError(
            f"corpus file not found at {target}; "
            "refusing to generate a Bee without a names corpus"
        )

    seen: set[tuple[str, str]] = set()
    out: list[CorpusEntry] = []

    for lineno, raw in enumerate(target.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) != 3:
            logger.warning(
                "corpus[%s]:%d skipped — expected 3 pipe-delimited fields, got %d",
                league, lineno, len(parts),
            )
            continue
        name, type_, display = (p.strip() for p in parts)

        if type_ not in VALID_TYPES:
            logger.warning(
                "corpus[%s]:%d skipped — unknown type %r (valid: %s)",
                league, lineno, type_, sorted(VALID_TYPES),
            )
            continue
        if not NAME_PATTERN.match(name):
            logger.warning(
                "corpus[%s]:%d skipped — name %r is not uppercase A–Z only",
                league, lineno, name,
            )
            continue
        if not (min_length <= len(name) <= max_length):
            # Not a warning — these are deliberately filtered for board fit.
            continue
        if not display:
            logger.warning(
                "corpus[%s]:%d skipped — empty display field",
                league, lineno,
            )
            continue

        key = (name, type_)
        if key in seen:
            continue
        seen.add(key)
        out.append(CorpusEntry(name=name, type=type_, display=display))  # type: ignore[arg-type]

    if not out:
        logger.warning("corpus[%s] loaded zero entries from %s", league, target)
    return out


def names_only(corpus: list[CorpusEntry]) -> set[str]:
    """Convenience: just the uppercase names, deduped across types.

    The Bee board validation only cares about whether a typed string
    matches *any* corpus entry — type and display are presentation
    concerns. This helper gives the matcher a fast lookup set.
    """
    return {entry.name for entry in corpus}
