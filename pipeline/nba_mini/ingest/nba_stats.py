"""nba.com box-score ingest for the previous day's slate.

Fetches the games played on a given calendar date (US/Eastern) and returns a
structured ``GamesDigest`` the puzzle generator can consume. If no games were
played that day, returns ``NoGamesSignal`` instead so the caller can distinguish
"no games" from "empty digest after filtering."

API surface
-----------
- ``fetch_yesterday_games(date) -> GamesDigest | NoGamesSignal``

Why a custom client abstraction?
--------------------------------
``nba_api`` is the de-facto Python wrapper for nba.com stats endpoints, but it
does live HTTP at construction time of each endpoint object. We therefore wrap
its two endpoints behind a small ``StatsClient`` Protocol so:

1. Tests inject a deterministic stub and never touch the network.
2. The retry/error-wrapping layer lives in *our* code, not ``nba_api``'s.
3. If ``nba_api`` ever changes shape we can swap it for a direct ``requests``
   client without touching the parser or the public API.

The default client (``NbaApiStatsClient``) imports ``nba_api`` lazily so the
module can be imported in environments where ``nba_api`` is missing — which is
exactly what the test suite does.

Scoreboard source: V3 adapted to the V2 shape
----------------------------------------------
The live scoreboard is fetched from **ScoreboardV3** (``nba_api`` documents V2
as unreliable — it served a ``None`` home-team id and a missing opponent row for
an NBA Finals game, crashing the parser). The V3 payload is reshaped into the
legacy V2 ``resultSets`` shape (``GameHeader`` + ``LineScore`` tables) by
``_v3_scoreboard_to_resultsets`` *at the client boundary*, so the parser
(``_parse_scoreboard``) and its test suite — which are written against the V2
shape — stay unchanged. The V2 ``resultSets`` form is therefore now a purely
**internal intermediate format**, not a live API source; the ``_RS_*`` constants
and the parser's field names (``GAME_DATE_EST``, ``LIVE_PERIOD``, …) describe
that intermediate shape, not a current nba.com response.

Caching
-------
Both scoreboard and per-game box-score responses are cached as raw JSON under
``$NBA_MINI_CACHE_DIR`` (default ``~/.cache/nba-mini/nba_stats/``). One file per
date for the scoreboard; one file per game id for box scores. Cache hits skip
the network entirely and are used liberally during development.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public models
# ---------------------------------------------------------------------------


class TopPerformer(BaseModel):
    """A standout player line from a single game."""

    model_config = ConfigDict(extra="forbid")
    player: Annotated[str, Field(min_length=1)]
    team: Annotated[str, Field(min_length=1)]
    statline: Annotated[str, Field(min_length=1)]
    """Pretty-printed statline, e.g. ``"32 PTS / 8 REB / 5 AST"``."""


class GameSummary(BaseModel):
    """One game's worth of consumable data for clue generation."""

    model_config = ConfigDict(extra="forbid")
    game_id: Annotated[str, Field(min_length=1)]
    home: Annotated[str, Field(min_length=1)]
    """Tri-code (e.g. ``BOS``)."""
    away: Annotated[str, Field(min_length=1)]
    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    score: Annotated[str, Field(min_length=1)]
    """Pretty-printed final, e.g. ``"BOS 112, NYK 109 (OT)"``."""
    top_performers: list[TopPerformer]
    series_context: str = ""
    """Playoff series grounding, e.g. ``"Western Conf Finals, Game 6 — Series
    tied 3-3"``. Empty for regular-season games or when nba.com doesn't serve it.

    nba.com has no prose recap endpoint, but it does serve the series state
    (round, game number, who leads). That's the single most hallucination-prone
    fact in a playoff clue, so grounding it here keeps clues honest. Populated
    best-effort: a fetch failure leaves it empty rather than failing the game."""
    notable_events: list[str]
    """Tags like ``"OT"``, ``"2OT"``, ``"BLOWOUT"``, ``"NAILBITER"``,
    ``"FOULED_OUT:LeBron James"``."""


class GamesDigest(BaseModel):
    """The full slate for a given date."""

    model_config = ConfigDict(extra="forbid")
    date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    games: list[GameSummary]


class NoGamesSignal(BaseModel):
    """Distinct return type for "the league did not play that day."

    Kept as a pydantic model (rather than a sentinel) so the caller's type check
    is symmetric with ``GamesDigest`` and so it round-trips through JSON cleanly
    if we ever want to log it.
    """

    model_config = ConfigDict(extra="forbid")
    kind: Literal["no_games"] = "no_games"
    date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NBAStatsError(Exception):
    """Base class for all nba.com ingest errors."""


class NBAStatsFetchError(NBAStatsError):
    """Raised after retries are exhausted for an HTTP-level failure."""


class NBAStatsParseError(NBAStatsError):
    """Raised when nba.com returns a response we cannot parse.

    Wraps the underlying ``KeyError``/``IndexError``/``TypeError`` so the
    pipeline can fail loudly and a human can investigate the schema change.
    """


# ---------------------------------------------------------------------------
# Client abstraction
# ---------------------------------------------------------------------------


class StatsClient(Protocol):
    """Minimal contract over the nba.com endpoints we use.

    ``fetch_summary`` is optional: it carries the playoff series context, which
    is best-effort grounding rather than core data. Clients (and test stubs)
    that don't implement it are fine — the caller probes with ``getattr`` and
    skips series context when it's absent.
    """

    def fetch_scoreboard(self, game_date: date_cls) -> dict[str, Any]: ...
    def fetch_boxscore(self, game_id: str) -> dict[str, Any]: ...


# nba.com league IDs. The same stats host serves both leagues; only the
# league_id query param differs. "00" = NBA, "10" = WNBA.
League = Literal["nba", "wnba"]
LEAGUE_IDS: dict[League, str] = {"nba": "00", "wnba": "10"}


class NbaApiStatsClient:
    """Default ``StatsClient`` backed by the ``nba_api`` package.

    Imports ``nba_api`` lazily so the module is importable in test/CI
    environments without the runtime dep. ``nba_api`` has a slightly quirky
    surface — each endpoint is a class that does the HTTP call in its
    constructor, then exposes ``.get_dict()`` for the parsed response.

    ``league`` selects which league's slate to fetch. It's bound at
    construction (not per call) so the ``StatsClient`` protocol stays a clean
    ``(game_date) -> payload`` shape and existing test stubs keep working
    unchanged.
    """

    def __init__(self, league: League = "nba") -> None:
        self.league = league
        self.league_id = LEAGUE_IDS[league]

    def fetch_scoreboard(self, game_date: date_cls) -> dict[str, Any]:
        from nba_api.stats.endpoints import scoreboardv3  # type: ignore[import-not-found]

        # ScoreboardV2 serves broken line-score data for some games (notably
        # playoff games: a None home-team id and a missing opponent row), which
        # crashed the Finals-Game-1 run on 2026-06-04. nba_api itself flags V2
        # as unreliable and points to V3 as the backward-compatible replacement.
        # We fetch V3 and adapt it to the V2 ``resultSets`` shape the parser
        # already consumes (see ``_v3_scoreboard_to_resultsets``), so the parser
        # and its test suite stay unchanged.
        endpoint = scoreboardv3.ScoreboardV3(
            game_date=game_date.isoformat(),
            league_id=self.league_id,
        )
        return _v3_scoreboard_to_resultsets(endpoint.get_dict())

    def fetch_boxscore(self, game_id: str) -> dict[str, Any]:
        from nba_api.stats.endpoints import boxscoretraditionalv2  # type: ignore[import-not-found]

        endpoint = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        return endpoint.get_dict()

    def fetch_summary(self, game_id: str) -> dict[str, Any]:
        """Game summary (carries playoff series state). Best-effort grounding.

        Uses BoxScoreSummaryV3 — its ``seriesText`` / ``gameLabel`` fields are
        the series context we ground playoff clues on. Has no regular-season
        signal, and the caller treats any failure as "no series context."
        """
        from nba_api.stats.endpoints import boxscoresummaryv3  # type: ignore[import-not-found]

        endpoint = boxscoresummaryv3.BoxScoreSummaryV3(game_id=game_id)
        return endpoint.get_dict()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    raw = os.environ.get("NBA_MINI_CACHE_DIR")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".cache" / "nba-mini" / "nba_stats"


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("ignoring corrupt cache at %s: %s", path, exc)
        return None


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryConfig:
    attempts: int = 3
    base_delay: float = 0.5
    """Seconds. Doubles each retry."""


def _is_retryable(exc: BaseException) -> bool:
    """A transient HTTP-style failure: 5xx, connection drop, timeout.

    Kept loose-but-explicit; we don't want to retry parse errors or 4xx.
    """
    name = type(exc).__name__
    if name in {"ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout"}:
        return True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int) and 500 <= status < 600:
        return True
    # ``requests.exceptions.HTTPError`` sometimes stringifies the status.
    msg = str(exc)
    return any(code in msg for code in ("500 ", "502 ", "503 ", "504 "))


def _with_retry(
    fn,
    *,
    label: str,
    config: RetryConfig,
    sleep=time.sleep,
):
    last: BaseException | None = None
    for attempt in range(1, config.attempts + 1):
        try:
            return fn()
        except NBAStatsParseError:
            raise
        except Exception as exc:  # noqa: BLE001 — we re-raise as a typed error below
            last = exc
            if not _is_retryable(exc) or attempt == config.attempts:
                break
            delay = config.base_delay * (2 ** (attempt - 1))
            logger.warning(
                "%s failed on attempt %d/%d (%s); retrying in %.1fs",
                label,
                attempt,
                config.attempts,
                exc,
                delay,
            )
            sleep(delay)
    raise NBAStatsFetchError(f"{label} failed after {config.attempts} attempts: {last}") from last


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

# Scoreboard fields we care about. These name the tables of the V2-style
# ``resultSets`` shape — now an *internal* intermediate format produced by
# ``_v3_scoreboard_to_resultsets`` (the live source is ScoreboardV3; see the
# module docstring). The GameHeader and LineScore tables together have
# everything we need to build a (game_id, home, away, scores, period) tuple
# without a box-score call. We still call boxscore for player lines.
_RS_GAME_HEADER = "GameHeader"
_RS_LINE_SCORE = "LineScore"
_RS_PLAYER_STATS = "PlayerStats"


def _index_result_sets(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    try:
        sets = payload["resultSets"]
    except (KeyError, TypeError) as exc:
        raise NBAStatsParseError(f"missing 'resultSets' in response: {exc}") from exc
    out: dict[str, dict[str, Any]] = {}
    for rs in sets:
        try:
            out[rs["name"]] = rs
        except (KeyError, TypeError) as exc:
            raise NBAStatsParseError(f"malformed resultSet entry: {exc}") from exc
    return out


def _rows_as_dicts(rs: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        headers: list[str] = rs["headers"]
        rows: list[list[Any]] = rs["rowSet"]
    except (KeyError, TypeError) as exc:
        raise NBAStatsParseError(f"resultSet missing headers/rowSet: {exc}") from exc
    return [dict(zip(headers, row, strict=False)) for row in rows]


def _parse_game_date(raw: Any) -> date_cls | None:
    """Parse ``GAME_DATE_EST`` (``"2026-05-30T00:00:00"``) into a date, or None."""
    if not raw:
        return None
    s = str(raw)
    # The date portion is always the leading 10 chars; the time/zone is noise.
    try:
        return date_cls.fromisoformat(s[:10])
    except ValueError:
        return None


def _v3_scoreboard_to_resultsets(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt a ScoreboardV3 payload into the V2 ``resultSets`` shape.

    The downstream parser (``_parse_scoreboard``) and its test suite are written
    against V2's ``GameHeader`` + ``LineScore`` tables. Rather than rewrite that
    well-tested parser, we reshape V3's cleaner ``scoreboard.games`` list into
    the same two tables. V3 is the source of truth for team ids, tri-codes, and
    scores (V2 omits or nulls them for some playoff games).

    A payload that doesn't look like V3 (no ``scoreboard.games``) is returned
    unchanged, so a V2-shaped fixture or an already-adapted payload passes
    through untouched — this keeps the function safe to call unconditionally.
    """
    scoreboard = payload.get("scoreboard")
    if not isinstance(scoreboard, dict) or "games" not in scoreboard:
        return payload

    header_rows: list[list[Any]] = []
    line_rows: list[list[Any]] = []
    for game in scoreboard.get("games") or []:
        game_id = game.get("gameId")
        home = game.get("homeTeam") or {}
        away = game.get("awayTeam") or {}

        # Skip a game missing the fields the parser must have (game id + both
        # teams' ids and tri-codes). Skipping one malformed game is strictly
        # better than letting its None values flow downstream, where a None
        # tri-code aborts the *entire* slate at GameSummary validation — the
        # same all-or-nothing failure this V3 switch exists to remove. A
        # genuinely empty slate still falls through to NoGamesSignal.
        if not (
            game_id
            and home.get("teamId") is not None
            and away.get("teamId") is not None
            and home.get("teamTricode")
            and away.get("teamTricode")
        ):
            logger.warning(
                "v3 scoreboard: skipping game %r with missing id/team fields "
                "(home=%r, away=%r)",
                game_id,
                home.get("teamTricode"),
                away.get("teamTricode"),
            )
            continue

        # V3 dates are ISO-with-zone (``2026-06-03T20:30:00Z``); the parser only
        # reads the leading 10 chars, so this drops straight into GAME_DATE_EST.
        game_date = game.get("gameEt") or game.get("gameTimeUTC")
        period = game.get("period")

        header_rows.append(
            [
                game_date,
                game_id,
                game.get("gameStatusText"),
                home.get("teamId"),
                away.get("teamId"),
                period,
            ]
        )
        for team in (home, away):
            line_rows.append(
                [
                    game_id,
                    team.get("teamId"),
                    team.get("teamTricode"),
                    team.get("score"),
                    period,
                ]
            )

    return {
        "resultSets": [
            {
                "name": _RS_GAME_HEADER,
                "headers": list(_ADAPTED_GAME_HEADER_COLUMNS),
                "rowSet": header_rows,
            },
            {
                "name": _RS_LINE_SCORE,
                "headers": list(_ADAPTED_LINE_SCORE_COLUMNS),
                "rowSet": line_rows,
            },
        ]
    }


# The exact column sets ``_v3_scoreboard_to_resultsets`` emits. These double as
# the cache-freshness signature: the live writer only ever persists payloads in
# this shape, so a cached scoreboard whose GameHeader columns differ predates the
# V3 switch (a raw ScoreboardV2 blob) and must be re-fetched, not parsed — feeding
# a stale raw-V2 payload to the parser is what crashed the June 2026 NBA slate
# with ``team None not found``. See ``_scoreboard_cache_is_fresh``.
_ADAPTED_GAME_HEADER_COLUMNS = (
    "GAME_DATE_EST",
    "GAME_ID",
    "GAME_STATUS_TEXT",
    "HOME_TEAM_ID",
    "VISITOR_TEAM_ID",
    "LIVE_PERIOD",
)
_ADAPTED_LINE_SCORE_COLUMNS = (
    "GAME_ID",
    "TEAM_ID",
    "TEAM_ABBREVIATION",
    "PTS",
    "LIVE_PERIOD",
)


def _scoreboard_is_final(payload: dict[str, Any]) -> bool:
    """True iff every game on an *adapted* scoreboard has finished.

    Reads GAME_STATUS_TEXT from the GameHeader table. A live scoreboard fetched
    before tip-off lists games as scheduled (``"8:30 pm ET"``) with 0-0 line
    scores; an in-progress one shows ``"Q3 5:42"``. Only ``Final`` (incl.
    ``Final/OT``) counts as settled. An empty slate is trivially settled (a real
    no-games day — safe to cache so the walk-back doesn't re-fetch it).

    Caching a non-final snapshot is the second half of the June 2026 stale-cache
    bug: the pre-tip-off 0-0 stub for NBA Finals Game 3 was persisted, so every
    later run read the stub from disk and skipped the real result forever.
    """
    sets = _index_result_sets(payload)
    if _RS_GAME_HEADER not in sets:
        return False
    rows = _rows_as_dicts(sets[_RS_GAME_HEADER])
    return all("final" in (row.get("GAME_STATUS_TEXT") or "").lower() for row in rows)


def _scoreboard_cache_is_fresh(payload: dict[str, Any]) -> bool:
    """Gate for reusing a cached scoreboard: current shape AND fully final.

    Rejects two stale-cache hazards (both hit the NBA slate in June 2026):

    1. **Wrong shape** — the live path only ever writes
       ``_v3_scoreboard_to_resultsets`` output, so a cached GameHeader whose
       columns aren't ``_ADAPTED_GAME_HEADER_COLUMNS`` is a pre-V3 raw blob.
       Re-fetch instead of feeding it to the parser (which would crash).
    2. **Not final** — a snapshot cached before tip-off (or mid-game) hides the
       real result. Re-fetch so the now-final slate replaces the stub.

    On any structural surprise, return False (re-fetch) rather than raising —
    a stale *cache* should never be the thing that aborts ingest.
    """
    try:
        sets = _index_result_sets(payload)
        header = sets.get(_RS_GAME_HEADER)
        if header is None:
            return False
        if tuple(header.get("headers") or ()) != _ADAPTED_GAME_HEADER_COLUMNS:
            return False
        return _scoreboard_is_final(payload)
    except NBAStatsParseError:
        return False


def _parse_scoreboard(
    payload: dict[str, Any], *, today: date_cls | None = None
) -> list[dict[str, Any]]:
    """Parse the scoreboard into per-game metadata for **prior** games.

    Returns ``{game_id, home/away_team, home/away_score, period}`` per game,
    where the scores may be ``None`` — nba.com routinely serves ``PTS=None`` on
    the scoreboard even for completed games, so the authoritative score is
    backfilled from the box score downstream. We do **not** coerce a missing
    score to 0 here (that was the fabricated-0-0 bug).

    ``today`` is the publish-date boundary: any game dated **on or after**
    ``today`` is a future/not-yet-played game and is dropped. This is the
    primary, reliable future-game gate ("use game dates less than today"); the
    box-score "was it actually played" check downstream is the backstop for
    postponed games dated in the past.
    """

    sets = _index_result_sets(payload)
    if _RS_GAME_HEADER not in sets:
        raise NBAStatsParseError(f"scoreboard missing '{_RS_GAME_HEADER}' set")
    headers = _rows_as_dicts(sets[_RS_GAME_HEADER])

    line_scores_by_team: dict[tuple[str, str], dict[str, Any]] = {}
    if _RS_LINE_SCORE in sets:
        for row in _rows_as_dicts(sets[_RS_LINE_SCORE]):
            try:
                line_scores_by_team[(row["GAME_ID"], row["TEAM_ABBREVIATION"])] = row
            except KeyError as exc:
                raise NBAStatsParseError(f"line score row missing key: {exc}") from exc

    games: list[dict[str, Any]] = []
    for header in headers:
        try:
            game_id = header["GAME_ID"]
            home_id = header["HOME_TEAM_ID"]
            away_id = header["VISITOR_TEAM_ID"]
        except KeyError as exc:
            raise NBAStatsParseError(f"game header missing key: {exc}") from exc

        # Future-game gate: drop anything dated on/after the publish date. A
        # game with no parseable date is kept (the box-score check still guards
        # it) rather than dropped on a formatting quirk.
        game_date = _parse_game_date(header.get("GAME_DATE_EST"))
        if today is not None and game_date is not None and game_date >= today:
            logger.info(
                "skipping future game %s dated %s (>= publish date %s)",
                game_id,
                game_date.isoformat(),
                today.isoformat(),
            )
            continue

        # The line score table uses team_id too; pull tri-codes + scores via id.
        home_line = _find_line_for_team(sets, game_id, home_id)
        away_line = _find_line_for_team(sets, game_id, away_id)

        home_pts = home_line.get("PTS")
        away_pts = away_line.get("PTS")

        games.append(
            {
                "game_id": game_id,
                "home_team": home_line["TEAM_ABBREVIATION"],
                "away_team": away_line["TEAM_ABBREVIATION"],
                # Scores stay None when the scoreboard omits them; the box score
                # is the source of truth and backfills downstream.
                "home_score": None if home_pts is None else int(home_pts),
                "away_score": None if away_pts is None else int(away_pts),
                # LIVE_PERIOD is "current period" for in-progress games and the
                # final period for completed games. Period > 4 → overtime.
                "period": int(home_line.get("LIVE_PERIOD") or header.get("LIVE_PERIOD") or 4),
            }
        )
    return games


def _find_line_for_team(
    sets: dict[str, dict[str, Any]], game_id: str, team_id: int | str
) -> dict[str, Any]:
    if _RS_LINE_SCORE not in sets:
        raise NBAStatsParseError(f"scoreboard missing '{_RS_LINE_SCORE}' set")
    for row in _rows_as_dicts(sets[_RS_LINE_SCORE]):
        if row.get("GAME_ID") == game_id and row.get("TEAM_ID") == team_id:
            return row
    raise NBAStatsParseError(
        f"line score for game {game_id} team {team_id} not found in response"
    )


def _parse_boxscore_players(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sets = _index_result_sets(payload)
    if _RS_PLAYER_STATS not in sets:
        raise NBAStatsParseError(f"boxscore missing '{_RS_PLAYER_STATS}' set")
    return _rows_as_dicts(sets[_RS_PLAYER_STATS])


_RS_TEAM_STATS = "TeamStats"


def _boxscore_was_played(player_rows: list[dict[str, Any]]) -> bool:
    """True iff at least one player logged minutes — i.e. the game happened.

    nba.com serves a stub box score (empty or all-zero-minute player rows) for
    a scheduled game that hasn't tipped off. This is the authoritative "did it
    actually happen" check, used as a backstop to the scoreboard date gate for
    postponed games that are dated in the past but never played.
    """
    return any(_parse_minutes(row.get("MIN")) > 0 for row in player_rows)


def _team_scores_from_boxscore(payload: dict[str, Any]) -> dict[str, int]:
    """Authoritative ``{tri_code: PTS}`` from the box score's TeamStats table.

    The scoreboard's line-score PTS is frequently ``None`` even for finished
    games; TeamStats carries the real final. Returns ``{}`` if the table is
    missing or unparseable (caller falls back to whatever the scoreboard had).
    """
    sets = _index_result_sets(payload)
    ts = sets.get(_RS_TEAM_STATS)
    if not ts:
        return {}
    out: dict[str, int] = {}
    for row in _rows_as_dicts(ts):
        tri = row.get("TEAM_ABBREVIATION")
        pts = row.get("PTS")
        if tri and pts is not None:
            try:
                out[str(tri)] = int(pts)
            except (TypeError, ValueError):
                continue
    return out


def _parse_series_context(summary_payload: dict[str, Any]) -> str:
    """Build a one-line playoff series-context string from a V3 summary payload.

    Returns ``""`` for regular-season games (no series text) or any payload
    shape we don't recognize — this is best-effort grounding, never a hard
    failure. Example output: ``"Western Conf Finals, Game 6 — Series tied 3-3"``.
    """
    summary = summary_payload.get("boxScoreSummary")
    if not isinstance(summary, dict):
        return ""

    series_text = str(summary.get("seriesText") or "").strip()
    game_number = str(summary.get("seriesGameNumber") or "").strip()
    # ``gameLabel`` is the round name ("Western Conf Finals"); ``gameSubLabel``
    # is sometimes the same series-text repeated, so we prefer the label.
    label = str(summary.get("gameLabel") or "").strip()

    if not (series_text or game_number or label):
        return ""

    head_parts = [p for p in (label, game_number) if p]
    head = ", ".join(head_parts)
    if head and series_text:
        return f"{head} — {series_text}"
    return head or series_text


# ---------------------------------------------------------------------------
# Top performers + notable events
# ---------------------------------------------------------------------------


def _parse_minutes(raw: Any) -> float:
    """``MIN`` comes back as ``"34:12"``, ``"34"``, ``None``, or ``""``."""
    if raw is None or raw == "":
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw)
    if ":" in s:
        m, _, sec = s.partition(":")
        try:
            return int(m) + int(sec) / 60
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _player_score(row: dict[str, Any]) -> float:
    """Lightweight game-score-ish heuristic for ranking standouts.

    Not John Hollinger's exact formula — just close enough to surface the
    obvious "this guy was the story" line.
    """
    pts = float(row.get("PTS") or 0)
    reb = float(row.get("REB") or 0)
    ast = float(row.get("AST") or 0)
    stl = float(row.get("STL") or 0)
    blk = float(row.get("BLK") or 0)
    to = float(row.get("TO") or 0)
    return pts + 0.4 * reb + 0.7 * ast + stl + 0.7 * blk - 0.4 * to


def _statline(row: dict[str, Any]) -> str:
    pts = int(row.get("PTS") or 0)
    reb = int(row.get("REB") or 0)
    ast = int(row.get("AST") or 0)
    parts = [f"{pts} PTS", f"{reb} REB", f"{ast} AST"]
    blk = int(row.get("BLK") or 0)
    stl = int(row.get("STL") or 0)
    if blk >= 3:
        parts.append(f"{blk} BLK")
    if stl >= 3:
        parts.append(f"{stl} STL")
    return " / ".join(parts)


def _player_name(row: dict[str, Any]) -> str:
    # ``PLAYER_NAME`` is the documented field; fall back to first/last if missing.
    name = row.get("PLAYER_NAME")
    if name:
        return str(name)
    first = row.get("FIRST_NAME") or ""
    last = row.get("LAST_NAME") or ""
    full = f"{first} {last}".strip()
    if not full:
        raise NBAStatsParseError("player row missing PLAYER_NAME and FIRST/LAST_NAME")
    return full


def _select_top_performers(
    rows: list[dict[str, Any]], home: str, away: str, limit_per_team: int = 1
) -> list[TopPerformer]:
    by_team: dict[str, list[dict[str, Any]]] = {home: [], away: []}
    for row in rows:
        team = row.get("TEAM_ABBREVIATION")
        if team in by_team and _parse_minutes(row.get("MIN")) > 0:
            by_team[team].append(row)
    out: list[TopPerformer] = []
    for team in (home, away):
        ranked = sorted(by_team[team], key=_player_score, reverse=True)
        for row in ranked[:limit_per_team]:
            out.append(
                TopPerformer(
                    player=_player_name(row),
                    team=str(team),
                    statline=_statline(row),
                )
            )
    return out


_BLOWOUT_MARGIN = 25
_NAILBITER_MARGIN = 3
_FOULED_OUT_PF = 6


def _detect_notable_events(
    home: str,
    away: str,
    home_score: int,
    away_score: int,
    period: int,
    player_rows: list[dict[str, Any]],
) -> list[str]:
    events: list[str] = []
    margin = abs(home_score - away_score)

    if period > 4:
        ot_count = period - 4
        events.append("OT" if ot_count == 1 else f"{ot_count}OT")

    if margin >= _BLOWOUT_MARGIN:
        winner = home if home_score > away_score else away
        events.append(f"BLOWOUT:{winner}")
    elif margin <= _NAILBITER_MARGIN and period >= 4:
        events.append("NAILBITER")

    # A real ejection isn't in the box score; a "fouled out" line is the closest
    # signal we have. The spec accepts that we'll miss true ejections (Reddit
    # ingest catches those).
    for row in player_rows:
        try:
            pf = int(row.get("PF") or 0)
        except (TypeError, ValueError):
            pf = 0
        if pf >= _FOULED_OUT_PF:
            try:
                events.append(f"FOULED_OUT:{_player_name(row)}")
            except NBAStatsParseError:
                # If the player name is missing on this row, skip the tag rather
                # than failing the whole digest.
                continue

    return events


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def _fetch_series_context(
    client: StatsClient,
    game_id: str,
    *,
    cache_dir: Path,
    retry: RetryConfig,
    sleep,
) -> str:
    """Best-effort playoff series context for a game. Never raises.

    Probes the client for an optional ``fetch_summary`` method (test stubs and
    older clients don't have it). Any failure — missing method, network error,
    unparseable payload — degrades to ``""`` and is logged, never propagated.
    Series context is grounding, not core data; a missing summary must not sink
    an otherwise-complete game.
    """
    fetch_summary = getattr(client, "fetch_summary", None)
    if not callable(fetch_summary):
        return ""

    summary_cache_path = cache_dir / f"summary-{game_id}.json"
    try:
        payload = _read_cache(summary_cache_path)
        if payload is None:
            payload = _with_retry(
                lambda: fetch_summary(game_id),
                label=f"summary {game_id}",
                config=retry,
                sleep=sleep,
            )
            _write_cache(summary_cache_path, payload)
        return _parse_series_context(payload)
    except Exception as exc:  # noqa: BLE001 — grounding is strictly best-effort
        logger.info("no series context for game %s: %s", game_id, exc)
        return ""


def fetch_yesterday_games(
    date: date_cls,
    *,
    league: League = "nba",
    today: date_cls | None = None,
    client: StatsClient | None = None,
    cache_dir: Path | None = None,
    retry: RetryConfig | None = None,
    sleep=time.sleep,
) -> GamesDigest | NoGamesSignal:
    """Fetch the slate played on ``date`` (US/Eastern) and return a digest.

    Only **already-played** games are returned. Two gates enforce that: games
    dated on or after ``today`` (the publish date) are dropped as future, and a
    game whose box score shows no minutes played is dropped as not-yet-tipped.
    Final scores are taken from the box score (the scoreboard's PTS is often
    ``None`` even for completed games), never fabricated as 0-0.

    Parameters
    ----------
    date:
        Calendar date to fetch (caller resolves "yesterday" in US/Eastern;
        nba.com's day boundary lines up with ET).
    today:
        The publish-date boundary for the future-game gate. Games dated on or
        after this are excluded. Defaults to ``date + 1`` (i.e. treat ``date``
        itself as a valid past day) when not supplied, preserving the original
        single-day behavior.
    league:
        Which league's slate to fetch — ``"nba"`` or ``"wnba"``. Selects the
        default client's ``league_id``. Ignored when ``client`` is given (the
        caller's stub already knows its league). Also namespaces the on-disk
        cache so the two leagues' scoreboards never collide.
    client:
        Override for the underlying nba.com fetcher. Tests pass a stub here.
        Defaults to ``NbaApiStatsClient(league)``.
    cache_dir:
        Override for the on-disk cache root. Defaults to
        ``$NBA_MINI_CACHE_DIR`` or ``~/.cache/nba-mini/nba_stats/``.
    retry:
        Override for retry/backoff config. Defaults to 3 attempts, 0.5s base.
    sleep:
        Injection seam for tests so they don't actually sleep on retry.

    Returns
    -------
    ``GamesDigest`` if any games were played; ``NoGamesSignal`` if zero.

    Raises
    ------
    NBAStatsFetchError
        nba.com 5xx after retries are exhausted, or any other transient HTTP
        failure that does not recover.
    NBAStatsParseError
        nba.com returned a response we don't know how to parse (likely an API
        change). We raise rather than silently producing wrong data.
    """
    client = client or NbaApiStatsClient(league)
    cache_dir = cache_dir or _cache_dir()
    retry = retry or RetryConfig()

    iso = date.isoformat()
    # Namespace the scoreboard cache by league so NBA and WNBA slates for the
    # same date don't overwrite each other. (Boxscore cache keys are by game
    # id, which is already globally unique across leagues.)
    sb_cache_path = cache_dir / f"scoreboard-{league}-{iso}.json"
    sb_payload = _read_cache(sb_cache_path)
    if sb_payload is not None and not _scoreboard_cache_is_fresh(sb_payload):
        # Stale cache: either a pre-V3 raw blob (wrong shape — would crash the
        # parser) or a pre-tip-off / in-progress snapshot (hides the real
        # result). Both bit the June 2026 NBA slate. Discard and re-fetch live.
        logger.info("scoreboard cache for %s %s is stale; re-fetching", league, iso)
        sb_payload = None
    if sb_payload is None:
        sb_payload = _with_retry(
            lambda: client.fetch_scoreboard(date),
            label=f"scoreboard {iso}",
            config=retry,
            sleep=sleep,
        )
        # Only persist a settled slate. Caching a non-final snapshot is what let
        # a pre-tip-off 0-0 stub mask a real game on every later run; an empty
        # slate is settled (a genuine no-games day) and safe to cache.
        if _scoreboard_is_final(sb_payload):
            _write_cache(sb_cache_path, sb_payload)
        else:
            logger.info(
                "not caching non-final scoreboard for %s %s (games scheduled/in-progress)",
                league,
                iso,
            )

    # Default the future-game boundary to date+1, so ``date`` itself counts as a
    # valid past day (the original single-day semantics).
    boundary = today if today is not None else date + timedelta(days=1)
    games_meta = _parse_scoreboard(sb_payload, today=boundary)
    if not games_meta:
        return NoGamesSignal(date=iso)

    summaries: list[GameSummary] = []
    for meta in games_meta:
        game_id = meta["game_id"]
        bs_cache_path = cache_dir / f"boxscore-{game_id}.json"
        bs_payload = _read_cache(bs_cache_path)
        if bs_payload is None:
            bs_payload = _with_retry(
                lambda gid=game_id: client.fetch_boxscore(gid),
                label=f"boxscore {game_id}",
                config=retry,
                sleep=sleep,
            )
            _write_cache(bs_cache_path, bs_payload)

        player_rows = _parse_boxscore_players(bs_payload)

        # Authoritative "did it actually happen" check: a scheduled game (dated
        # in the past but postponed, or a stub the scoreboard listed) has a box
        # score with no minutes played. Skip it rather than emit a 0-0 result.
        if not _boxscore_was_played(player_rows):
            logger.info(
                "skipping game %s: box score shows no minutes played (not tipped off)",
                game_id,
            )
            continue

        # Backfill scores from the box score's TeamStats — the scoreboard's PTS
        # is frequently None even for finished games. Fall back to whatever the
        # scoreboard had (then 0 as a last resort, though a played game always
        # has a TeamStats total).
        team_scores = _team_scores_from_boxscore(bs_payload)
        home_score = team_scores.get(meta["home_team"], meta["home_score"]) or 0
        away_score = team_scores.get(meta["away_team"], meta["away_score"]) or 0

        top_performers = _select_top_performers(
            player_rows, home=meta["home_team"], away=meta["away_team"]
        )
        notable = _detect_notable_events(
            home=meta["home_team"],
            away=meta["away_team"],
            home_score=home_score,
            away_score=away_score,
            period=meta["period"],
            player_rows=player_rows,
        )

        score_str = _format_score(
            meta["home_team"],
            home_score,
            meta["away_team"],
            away_score,
            period=meta["period"],
        )

        series_context = _fetch_series_context(
            client, game_id, cache_dir=cache_dir, retry=retry, sleep=sleep
        )

        summaries.append(
            GameSummary(
                game_id=game_id,
                home=meta["home_team"],
                away=meta["away_team"],
                home_score=home_score,
                away_score=away_score,
                score=score_str,
                top_performers=top_performers,
                series_context=series_context,
                notable_events=notable,
            )
        )

    # Every game on the scoreboard may have been filtered out (all future, or
    # all unplayed stubs). An empty digest is meaningless — signal no-games so
    # the walk-back keeps looking and the caller short-circuits correctly.
    if not summaries:
        return NoGamesSignal(date=iso)

    return GamesDigest(date=iso, games=summaries)


# How many days to walk back looking for the most recent slate before giving
# up. A league's longest in-season gap (All-Star break, Finals off-days) is a
# handful of days; 10 is comfortably beyond that without being unbounded.
MAX_LOOKBACK_DAYS = 10


def fetch_most_recent_games(
    start: date_cls,
    *,
    league: League = "nba",
    max_lookback: int = MAX_LOOKBACK_DAYS,
    client: StatsClient | None = None,
    cache_dir: Path | None = None,
    retry: RetryConfig | None = None,
    sleep=time.sleep,
) -> GamesDigest | NoGamesSignal:
    """Find the most recent day at or before ``start`` that had games.

    Walks back day-by-day from ``start`` (inclusive), returning the first
    ``GamesDigest`` it finds. This is what lets a puzzle published on Monday
    look back to Saturday's NBA slate or Sunday's WNBA slate — whichever was
    that league's most recent game day — instead of assuming "yesterday."

    Returns ``NoGamesSignal`` (dated to ``start``) if no games are found in the
    whole ``max_lookback`` window — e.g. a true off-season, or a league on a
    long break. The caller treats that exactly like the old no-games day.

    The single underlying client is reused across all probed days so the
    bound ``league_id`` and the on-disk cache are shared; each probed date
    still gets its own league-namespaced scoreboard cache entry.
    """
    probe_client = client or NbaApiStatsClient(league)
    for delta in range(max_lookback + 1):
        day = start - timedelta(days=delta)
        result = fetch_yesterday_games(
            day,
            league=league,
            today=start,
            client=probe_client,
            cache_dir=cache_dir,
            retry=retry,
            sleep=sleep,
        )
        if isinstance(result, GamesDigest):
            if delta:
                logger.info(
                    "%s: most recent games were %d day(s) before %s, on %s",
                    league,
                    delta,
                    start.isoformat(),
                    day.isoformat(),
                )
            return result
    logger.info(
        "%s: no games in the %d days up to %s",
        league,
        max_lookback,
        start.isoformat(),
    )
    return NoGamesSignal(date=start.isoformat())


def fetch_recent_games(
    start: date_cls,
    *,
    league: League = "nba",
    window_days: int = 3,
    max_lookback: int = MAX_LOOKBACK_DAYS,
    client: StatsClient | None = None,
    cache_dir: Path | None = None,
    retry: RetryConfig | None = None,
    sleep=time.sleep,
) -> GamesDigest | NoGamesSignal:
    """Gather the league's games over a multi-day recency window.

    Where :func:`fetch_most_recent_games` returns a single slate, this returns
    the games from the most recent slate **plus** the preceding ``window_days``
    of slates merged into one digest — a richer, more "current events" pool for
    clue generation than one night's box scores.

    The walk-back to find the *first* game day reuses ``fetch_most_recent_games``
    (so the off-season / long-break short-circuit and lookback bound are shared).
    From that most-recent slate date we then collect each prior day within the
    window that also had games. The resulting digest is **dated to the most
    recent slate** — that's the ``slate_date`` the puzzle records — while its
    ``games`` list spans the window.

    Returns ``NoGamesSignal`` (dated to ``start``) when the league has no games
    anywhere in the lookback window, exactly like ``fetch_most_recent_games``.
    """
    probe_client = client or NbaApiStatsClient(league)
    most_recent = fetch_most_recent_games(
        start,
        league=league,
        max_lookback=max_lookback,
        client=probe_client,
        cache_dir=cache_dir,
        retry=retry,
        sleep=sleep,
    )
    if isinstance(most_recent, NoGamesSignal):
        return most_recent

    anchor = date_cls.fromisoformat(most_recent.date)
    games: list[GameSummary] = list(most_recent.games)
    # Walk the days strictly before the anchor, within the window, merging any
    # that also had games. Days with no games are simply skipped — a quiet
    # Tuesday inside the window doesn't end the walk.
    for delta in range(1, window_days):
        day = anchor - timedelta(days=delta)
        result = fetch_yesterday_games(
            day,
            league=league,
            today=start,
            client=probe_client,
            cache_dir=cache_dir,
            retry=retry,
            sleep=sleep,
        )
        if isinstance(result, GamesDigest):
            games.extend(result.games)

    logger.info(
        "%s: recent-games window collected %d game(s) across up to %d day(s) ending %s",
        league,
        len(games),
        window_days,
        most_recent.date,
    )
    return GamesDigest(date=most_recent.date, games=games)


def _format_score(home: str, home_score: int, away: str, away_score: int, period: int) -> str:
    if home_score >= away_score:
        head = f"{home} {home_score}, {away} {away_score}"
    else:
        head = f"{away} {away_score}, {home} {home_score}"
    if period > 4:
        ot = period - 4
        head += " (OT)" if ot == 1 else f" ({ot}OT)"
    return head


__all__ = [
    "GamesDigest",
    "GameSummary",
    "League",
    "LEAGUE_IDS",
    "NbaApiStatsClient",
    "NBAStatsError",
    "NBAStatsFetchError",
    "NBAStatsParseError",
    "NoGamesSignal",
    "RetryConfig",
    "StatsClient",
    "TopPerformer",
    "fetch_most_recent_games",
    "fetch_recent_games",
    "fetch_yesterday_games",
]
