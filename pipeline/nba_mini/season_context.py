"""Loader for the hand-maintained season context snippet.

The markdown file is human-authored; the loader returns plaintext (markdown is
for editing affordance only — we don't render it). The version is a short
content hash so the puzzle JSON can record exactly which season-context
revision a given puzzle was generated against.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "season_context.md"
VERSION_HASH_LENGTH = 8


class SeasonContextNotFoundError(FileNotFoundError):
    """Raised when the season context markdown file is missing.

    Generation must not proceed without season context — the clue prompt
    depends on it for calendar framing (R3). Failing loud here is preferable
    to silently shipping a tone-deaf puzzle.
    """


@dataclass(frozen=True)
class SeasonContext:
    """The loaded season context: text body plus a stable version tag."""

    text: str
    version: str


def load_season_context(path: Path | None = None) -> SeasonContext:
    """Load the season context markdown and compute its version hash.

    Args:
        path: Optional override for the markdown path. Defaults to the
            packaged `season_context.md` next to this module.

    Returns:
        A `SeasonContext` carrying the file's text and an 8-char sha256 prefix
        of its bytes. Stable for unchanged content; changes when the file
        changes.

    Raises:
        SeasonContextNotFoundError: if the file does not exist.
    """
    target = path if path is not None else DEFAULT_PATH
    try:
        raw_bytes = target.read_bytes()
    except FileNotFoundError as exc:
        raise SeasonContextNotFoundError(
            f"season context file not found at {target}; "
            "refusing to generate a puzzle without season framing"
        ) from exc

    version = hashlib.sha256(raw_bytes).hexdigest()[:VERSION_HASH_LENGTH]
    return SeasonContext(text=raw_bytes.decode("utf-8"), version=version)
