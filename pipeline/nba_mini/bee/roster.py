"""Programmatic roster sourcing for the Bee corpus.

Hits ``nba_api``'s ``commonallplayers`` endpoint to pull every player
who's currently rostered (or in the historical index, depending on the
``is_only_current_season`` flag). The fetcher is wrapped behind a
``RosterClient`` Protocol so tests can inject a stub instead of hitting
nba.com.

Naming normalization:
- Last name only (the player record's display name is "First Last" or
  occasionally "First M. Last Jr." — we take the final whitespace-separated
  segment and strip suffixes like Jr./Sr./III).
- Diacritics stripped (Dončić → DONCIC) using NFKD decomposition.
- Punctuation (apostrophes, hyphens, dots) removed.
- Uppercase A-Z only.
- Length filter: 4-10 letters (the Bee corpus's structural window).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Literal, Protocol

logger = logging.getLogger(__name__)

League = Literal["nba", "wnba"]

# nba_api supports a `league_id` parameter on commonallplayers.
# "00" = NBA, "10" = WNBA, "20" = G League.
_LEAGUE_IDS: dict[League, str] = {"nba": "00", "wnba": "10"}

# Suffixes we strip from the final whitespace-separated segment before
# treating it as the last name. The endpoint returns "First Last Jr."-style
# strings, and we want the last *name*, not "Jr.".
_SUFFIXES = {"JR", "SR", "II", "III", "IV"}

_NON_LETTER = re.compile(r"[^A-Z]")
_MIN_LEN = 4
_MAX_LEN = 10


class RosterFetchError(RuntimeError):
    """Raised when the roster endpoint can't be reached or parsed."""


@dataclass(frozen=True)
class RosterPlayer:
    """A normalized record from the roster endpoint."""

    last_name: str
    """Uppercase, A-Z only, length ∈ [4, 10]."""
    display: str
    """Original "First Last" form, for the corpus DISPLAY column."""


class RosterClient(Protocol):
    """The single seam between this module and nba_api.

    Returns rows of ``(display_name, is_active)`` for each player. We
    accept a single tuple shape so tests can inject canned data without
    having to mimic ``nba_api``'s frame structure.
    """

    def fetch(self, league: League, *, only_active: bool) -> list[tuple[str, bool]]:
        ...


class NbaApiRosterClient:
    """Default client backed by ``nba_api.stats.endpoints.commonallplayers``.

    Imports ``nba_api`` lazily so this module is importable in environments
    without the dep — same pattern as ``ingest/nba_stats.py``.
    """

    def fetch(self, league: League, *, only_active: bool) -> list[tuple[str, bool]]:
        try:
            from nba_api.stats.endpoints import commonallplayers  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RosterFetchError(
                "nba_api is not installed; can't pull rosters live"
            ) from exc

        try:
            ep = commonallplayers.CommonAllPlayers(
                league_id=_LEAGUE_IDS[league],
                is_only_current_season=1 if only_active else 0,
            )
            data = ep.get_normalized_dict()
        except Exception as exc:
            raise RosterFetchError(
                f"failed to fetch {league} roster: {exc}"
            ) from exc

        # The endpoint's normalized dict has a top-level "CommonAllPlayers"
        # key with a list of row dicts. Each row carries DISPLAY_FIRST_LAST
        # (or DISPLAY_LAST_COMMA_FIRST) and ROSTERSTATUS (1 if active).
        rows = data.get("CommonAllPlayers", [])
        out: list[tuple[str, bool]] = []
        for row in rows:
            display = (
                row.get("DISPLAY_FIRST_LAST")
                or row.get("DISPLAY_FI_LAST")
                or ""
            )
            if not display:
                continue
            active = bool(row.get("ROSTERSTATUS", 0))
            out.append((display, active))
        return out


def normalize_last_name(display: str) -> str | None:
    """Extract the uppercase A-Z last name from a "First Last" string.

    Returns None if no usable last name comes out (length out of window,
    purely non-letters after normalization, etc.).
    """
    if not display or not isinstance(display, str):
        return None

    # Strip diacritics (Dončić → Doncic, Šengün → Sengun).
    deaccented = unicodedata.normalize("NFKD", display)
    deaccented = "".join(c for c in deaccented if not unicodedata.combining(c))

    # Split on whitespace; walk backward past any suffix tokens.
    parts = deaccented.strip().split()
    if not parts:
        return None
    while parts and _strip_punct(parts[-1]).upper() in _SUFFIXES:
        parts.pop()
    if not parts:
        return None
    last = parts[-1]

    # Uppercase + drop anything that isn't A-Z (apostrophes, hyphens, dots).
    last = _NON_LETTER.sub("", last.upper())

    if not (_MIN_LEN <= len(last) <= _MAX_LEN):
        return None
    return last


def _strip_punct(token: str) -> str:
    return _NON_LETTER.sub("", token.upper())


def fetch_roster(
    league: League,
    *,
    only_active: bool = True,
    client: RosterClient | None = None,
) -> list[RosterPlayer]:
    """Pull and normalize the roster for a league.

    Args:
        league: ``"nba"`` or ``"wnba"``.
        only_active: When True (default), restrict to currently-rostered
            players. When False, include the full historical index — used
            for an annual deep refresh.
        client: Inject a custom ``RosterClient`` for tests.

    Returns:
        Deduped list of ``RosterPlayer`` (key: normalized last name).
        Players whose normalized last name falls outside [4, 10] letters
        are silently dropped — they couldn't appear on a Bee board.
    """
    real_client: RosterClient = client if client is not None else NbaApiRosterClient()
    rows = real_client.fetch(league, only_active=only_active)

    seen: set[str] = set()
    out: list[RosterPlayer] = []
    for display, _active in rows:
        last = normalize_last_name(display)
        if last is None:
            continue
        if last in seen:
            continue
        seen.add(last)
        out.append(RosterPlayer(last_name=last, display=display.strip()))

    logger.info(
        "fetched %d roster players for %s (only_active=%s, %d unique last names)",
        len(rows), league, only_active, len(out),
    )
    return out


def to_corpus_lines(players: Iterable[RosterPlayer]) -> list[str]:
    """Format players as ``NAME|last|DISPLAY`` lines for the corpus file.

    The lines are NOT terminated with newlines — the caller decides how
    to write them out (in-place merge or full rewrite).
    """
    return [f"{p.last_name}|last|{p.display}" for p in players]
