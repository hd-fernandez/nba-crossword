"""Wordlist loader for the grid fill algorithm.

The wordlist is a plain text file: one ALL-CAPS word per line, blank lines and
`#`-prefixed comment lines ignored. The loader is defensive — it silently
filters out malformed entries (lowercase, non-letters, off-spec lengths) so
that authoring the file by hand stays easy and robust to small typos.

For v0, only word lengths {3, 4, 5} are useful (the 5x5 mini grids cannot
contain entries shorter than 2 or longer than 5). The loader exposes a
`min_length`/`max_length` filter so callers can be explicit.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "wordlist.txt"
MIN_USEFUL_LENGTH = 2
MAX_USEFUL_LENGTH = 5


class WordlistNotFoundError(FileNotFoundError):
    """Raised when the wordlist file is missing.

    Generation must not proceed without a wordlist — the fill algorithm
    has nothing to fall back on. Failing loud is preferable to silently
    shipping an unfillable grid.
    """


def _is_valid_word(token: str, min_length: int, max_length: int) -> bool:
    """A word is valid when it's all A-Z and falls within the length window."""
    if not token:
        return False
    if not (min_length <= len(token) <= max_length):
        return False
    return token.isascii() and token.isalpha() and token.isupper()


def load_wordlist(
    path: Path | None = None,
    *,
    min_length: int = MIN_USEFUL_LENGTH,
    max_length: int = MAX_USEFUL_LENGTH,
) -> list[str]:
    """Load and normalize the wordlist from disk.

    Args:
        path: Optional override for the wordlist file. Defaults to
            `pipeline/data/wordlist.txt` next to this package.
        min_length: Minimum word length to retain (inclusive). Defaults to 2.
        max_length: Maximum word length to retain (inclusive). Defaults to 5.

    Returns:
        A deduplicated, sorted list of uppercase ASCII words within the
        requested length window. Sorting makes the output deterministic
        across operating systems (file order from `splitlines` is stable
        but downstream fill is happier with a canonical order).

    Raises:
        WordlistNotFoundError: if the wordlist file does not exist.
        ValueError: if `min_length` > `max_length`.
    """
    if min_length > max_length:
        raise ValueError(
            f"min_length ({min_length}) must be <= max_length ({max_length})"
        )

    target = path if path is not None else DEFAULT_PATH
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WordlistNotFoundError(
            f"wordlist file not found at {target}; "
            "the grid fill algorithm cannot run without one"
        ) from exc

    seen: set[str] = set()
    words: list[str] = []
    for raw in text.splitlines():
        token = raw.strip()
        if not token or token.startswith("#"):
            continue
        # Be permissive about case in the file; canonicalize here.
        token = token.upper()
        if not _is_valid_word(token, min_length, max_length):
            continue
        if token in seen:
            continue
        seen.add(token)
        words.append(token)

    words.sort()
    return words


def filter_by_length(words: Iterable[str], length: int) -> list[str]:
    """Convenience: return only the words matching `length`."""
    return [w for w in words if len(w) == length]
