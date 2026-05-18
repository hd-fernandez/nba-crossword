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
    """Minimal contract over the two nba.com endpoints we use."""

    def fetch_scoreboard(self, game_date: date_cls) -> dict[str, Any]: ...
    def fetch_boxscore(self, game_id: str) -> dict[str, Any]: ...


class NbaApiStatsClient:
    """Default ``StatsClient`` backed by the ``nba_api`` package.

    Imports ``nba_api`` lazily so the module is importable in test/CI
    environments without the runtime dep. ``nba_api`` has a slightly quirky
    surface — each endpoint is a class that does the HTTP call in its
    constructor, then exposes ``.get_dict()`` for the parsed response.
    """

    def fetch_scoreboard(self, game_date: date_cls) -> dict[str, Any]:
        from nba_api.stats.endpoints import scoreboardv2  # type: ignore[import-not-found]

        endpoint = scoreboardv2.ScoreboardV2(
            game_date=game_date.isoformat(),
            league_id="00",
            day_offset=0,
        )
        return endpoint.get_dict()

    def fetch_boxscore(self, game_id: str) -> dict[str, Any]:
        from nba_api.stats.endpoints import boxscoretraditionalv2  # type: ignore[import-not-found]

        endpoint = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
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

# Scoreboard fields we care about. ``nba_api`` returns ``resultSets`` with named
# tables; the GameHeader and LineScore tables together have everything we need
# to build a (game_id, home, away, scores, period) tuple without a box-score
# call. We still call boxscore for player lines.
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


def _parse_scoreboard(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of ``{game_id, home_team, away_team, home_score, away_score, period}``."""

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

        # The line score table uses team_id too; pull tri-codes + scores via id.
        home_line = _find_line_for_team(sets, game_id, home_id)
        away_line = _find_line_for_team(sets, game_id, away_id)

        games.append(
            {
                "game_id": game_id,
                "home_team": home_line["TEAM_ABBREVIATION"],
                "away_team": away_line["TEAM_ABBREVIATION"],
                "home_score": int(home_line.get("PTS") or 0),
                "away_score": int(away_line.get("PTS") or 0),
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


def fetch_yesterday_games(
    date: date_cls,
    *,
    client: StatsClient | None = None,
    cache_dir: Path | None = None,
    retry: RetryConfig | None = None,
    sleep=time.sleep,
) -> GamesDigest | NoGamesSignal:
    """Fetch the slate played on ``date`` (US/Eastern) and return a digest.

    Parameters
    ----------
    date:
        Calendar date to fetch (caller resolves "yesterday" in US/Eastern;
        nba.com's day boundary lines up with ET).
    client:
        Override for the underlying nba.com fetcher. Tests pass a stub here.
        Defaults to ``NbaApiStatsClient()``.
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
    client = client or NbaApiStatsClient()
    cache_dir = cache_dir or _cache_dir()
    retry = retry or RetryConfig()

    iso = date.isoformat()
    sb_cache_path = cache_dir / f"scoreboard-{iso}.json"
    sb_payload = _read_cache(sb_cache_path)
    if sb_payload is None:
        sb_payload = _with_retry(
            lambda: client.fetch_scoreboard(date),
            label=f"scoreboard {iso}",
            config=retry,
            sleep=sleep,
        )
        _write_cache(sb_cache_path, sb_payload)

    games_meta = _parse_scoreboard(sb_payload)
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
        top_performers = _select_top_performers(
            player_rows, home=meta["home_team"], away=meta["away_team"]
        )
        notable = _detect_notable_events(
            home=meta["home_team"],
            away=meta["away_team"],
            home_score=meta["home_score"],
            away_score=meta["away_score"],
            period=meta["period"],
            player_rows=player_rows,
        )

        score_str = _format_score(
            meta["home_team"],
            meta["home_score"],
            meta["away_team"],
            meta["away_score"],
            period=meta["period"],
        )
        summaries.append(
            GameSummary(
                game_id=game_id,
                home=meta["home_team"],
                away=meta["away_team"],
                home_score=meta["home_score"],
                away_score=meta["away_score"],
                score=score_str,
                top_performers=top_performers,
                notable_events=notable,
            )
        )

    return GamesDigest(date=iso, games=summaries)


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
    "NbaApiStatsClient",
    "NBAStatsError",
    "NBAStatsFetchError",
    "NBAStatsParseError",
    "NoGamesSignal",
    "RetryConfig",
    "StatsClient",
    "TopPerformer",
    "fetch_yesterday_games",
]
