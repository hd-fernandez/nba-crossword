"""Tests for the nba.com box-score ingest.

We never hit live nba.com here — the production client is replaced by a
``StubStatsClient`` that returns hand-crafted payloads. The recorded fixture
file (``nba_stats_scoreboard.json``) carries the multi-game happy-path
scoreboard; per-game box scores and other scenarios are constructed inline so
a reader can see exactly which fields drive each assertion.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from nba_mini.ingest.nba_stats import (
    GamesDigest,
    LEAGUE_IDS,
    NbaApiStatsClient,
    NoGamesSignal,
    NBAStatsFetchError,
    NBAStatsParseError,
    RetryConfig,
    fetch_most_recent_games,
    fetch_recent_games,
    fetch_yesterday_games,
)

FIXTURES = Path(__file__).parent / "fixtures"
SCOREBOARD_FIXTURE = FIXTURES / "nba_stats_scoreboard.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_scoreboard_fixture() -> dict[str, Any]:
    return json.loads(SCOREBOARD_FIXTURE.read_text())


def _empty_scoreboard() -> dict[str, Any]:
    return {
        "resultSets": [
            {
                "name": "GameHeader",
                "headers": [
                    "GAME_DATE_EST",
                    "GAME_ID",
                    "GAME_STATUS_TEXT",
                    "HOME_TEAM_ID",
                    "VISITOR_TEAM_ID",
                    "LIVE_PERIOD",
                ],
                "rowSet": [],
            },
            {
                "name": "LineScore",
                "headers": [
                    "GAME_ID",
                    "TEAM_ID",
                    "TEAM_ABBREVIATION",
                    "PTS",
                    "LIVE_PERIOD",
                ],
                "rowSet": [],
            },
        ]
    }


def _player_row(
    team: str,
    name: str,
    *,
    minutes: str = "34:12",
    pts: int = 0,
    reb: int = 0,
    ast: int = 0,
    stl: int = 0,
    blk: int = 0,
    to: int = 0,
    pf: int = 2,
) -> dict[str, Any]:
    return {
        "GAME_ID": "0042500301",
        "TEAM_ID": 0,
        "TEAM_ABBREVIATION": team,
        "PLAYER_ID": 0,
        "PLAYER_NAME": name,
        "MIN": minutes,
        "PTS": pts,
        "REB": reb,
        "AST": ast,
        "STL": stl,
        "BLK": blk,
        "TO": to,
        "PF": pf,
    }


def _boxscore_payload(player_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resultSets": [
            {
                "name": "PlayerStats",
                "headers": list(player_rows[0].keys()) if player_rows else [],
                "rowSet": [list(row.values()) for row in player_rows],
            }
        ]
    }


class StubStatsClient:
    """Test double for ``StatsClient``.

    Records call counts so tests can assert cache hits skip the network.
    """

    def __init__(
        self,
        *,
        scoreboard: dict[str, Any] | Exception,
        boxscores: dict[str, dict[str, Any] | Exception],
    ) -> None:
        self.scoreboard_payload = scoreboard
        self.boxscore_payloads = boxscores
        self.scoreboard_calls = 0
        self.boxscore_calls: list[str] = []

    def fetch_scoreboard(self, game_date: date) -> dict[str, Any]:
        self.scoreboard_calls += 1
        if isinstance(self.scoreboard_payload, Exception):
            raise self.scoreboard_payload
        return copy.deepcopy(self.scoreboard_payload)

    def fetch_boxscore(self, game_id: str) -> dict[str, Any]:
        self.boxscore_calls.append(game_id)
        payload = self.boxscore_payloads[game_id]
        if isinstance(payload, Exception):
            raise payload
        return copy.deepcopy(payload)


class FlakyClient:
    """Fails N times then succeeds — for retry/backoff tests."""

    def __init__(self, fail_n: int, exc: Exception, then: dict[str, Any]) -> None:
        self.fail_n = fail_n
        self.exc = exc
        self.then = then
        self.scoreboard_calls = 0

    def fetch_scoreboard(self, game_date: date) -> dict[str, Any]:
        self.scoreboard_calls += 1
        if self.scoreboard_calls <= self.fail_n:
            raise self.exc
        return copy.deepcopy(self.then)

    def fetch_boxscore(self, game_id: str) -> dict[str, Any]:  # pragma: no cover
        raise AssertionError("scoreboard error path should not reach boxscore")


def _no_sleep(_seconds: float) -> None:
    return None


# Default boxscores for the two-game fixture: BOS-NYK and DEN-LAL.
def _default_boxscores() -> dict[str, dict[str, Any]]:
    bos_nyk = _boxscore_payload(
        [
            _player_row("BOS", "Jayson Tatum", pts=32, reb=8, ast=5, blk=1, pf=3),
            _player_row("BOS", "Jaylen Brown", pts=24, reb=6, ast=3, pf=4),
            _player_row("NYK", "Jalen Brunson", pts=28, reb=4, ast=9, pf=3),
            _player_row("NYK", "OG Anunoby", pts=14, reb=5, ast=2, pf=2),
        ]
    )
    den_lal = _boxscore_payload(
        [
            _player_row("DEN", "Nikola Jokic", pts=35, reb=14, ast=11, pf=2),
            _player_row("DEN", "Jamal Murray", pts=22, reb=3, ast=6, pf=3),
            _player_row("LAL", "Luka Doncic", pts=26, reb=7, ast=8, pf=4),
            _player_row("LAL", "Austin Reaves", pts=16, reb=4, ast=5, pf=2),
        ]
    )
    return {"0042500301": bos_nyk, "0042500302": den_lal}


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_two_game_slate_returns_digest_with_top_performers(tmp_path: Path) -> None:
    client = StubStatsClient(
        scoreboard=_load_scoreboard_fixture(),
        boxscores=_default_boxscores(),
    )

    result = fetch_yesterday_games(
        date(2026, 5, 14),
        client=client,
        cache_dir=tmp_path,
        sleep=_no_sleep,
    )

    assert isinstance(result, GamesDigest)
    assert result.date == "2026-05-14"
    assert len(result.games) == 2

    bos_nyk = next(g for g in result.games if g.game_id == "0042500301")
    assert bos_nyk.home == "BOS"
    assert bos_nyk.away == "NYK"
    assert bos_nyk.home_score == 112
    assert bos_nyk.away_score == 105
    assert bos_nyk.score.startswith("BOS 112, NYK 105")
    # Top performer per team — by PTS-driven score, Tatum and Brunson win out.
    players = {p.player for p in bos_nyk.top_performers}
    assert "Jayson Tatum" in players
    assert "Jalen Brunson" in players


def test_single_game_playoff_night_returns_one_game(tmp_path: Path) -> None:
    sb = _load_scoreboard_fixture()
    # Trim to game 0042500301 only.
    sb["resultSets"][0]["rowSet"] = sb["resultSets"][0]["rowSet"][:1]
    sb["resultSets"][1]["rowSet"] = [
        row for row in sb["resultSets"][1]["rowSet"] if row[0] == "0042500301"
    ]

    client = StubStatsClient(
        scoreboard=sb,
        boxscores={"0042500301": _default_boxscores()["0042500301"]},
    )
    result = fetch_yesterday_games(
        date(2026, 5, 14), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )

    assert isinstance(result, GamesDigest)
    assert len(result.games) == 1
    assert result.games[0].game_id == "0042500301"


# ---------------------------------------------------------------------------
# No-games signal
# ---------------------------------------------------------------------------


def test_no_games_day_returns_signal_not_empty_digest(tmp_path: Path) -> None:
    client = StubStatsClient(scoreboard=_empty_scoreboard(), boxscores={})

    result = fetch_yesterday_games(
        date(2026, 7, 5), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )

    assert isinstance(result, NoGamesSignal)
    assert not isinstance(result, GamesDigest)
    assert result.date == "2026-07-05"
    assert result.kind == "no_games"
    # No box-score calls when there are no games.
    assert client.boxscore_calls == []


# ---------------------------------------------------------------------------
# Notable events
# ---------------------------------------------------------------------------


def _set_field(rs: dict[str, Any], match: dict[str, Any], field: str, value: Any) -> None:
    """Set ``field`` to ``value`` for every row in ``rs`` whose values match.

    Drives field index off the result set's headers so tests stay readable when
    the fixture's column order changes.
    """
    headers: list[str] = rs["headers"]
    field_idx = headers.index(field)
    match_idx = {headers.index(k): v for k, v in match.items()}
    for row in rs["rowSet"]:
        if all(row[i] == v for i, v in match_idx.items()):
            row[field_idx] = value


def test_overtime_game_is_flagged_in_notable_events(tmp_path: Path) -> None:
    sb = _load_scoreboard_fixture()
    header_set = sb["resultSets"][0]
    line_set = sb["resultSets"][1]
    # Bump game 1 to OT (LIVE_PERIOD=5) in both tables.
    _set_field(header_set, {"GAME_ID": "0042500301"}, "LIVE_PERIOD", 5)
    _set_field(line_set, {"GAME_ID": "0042500301"}, "LIVE_PERIOD", 5)
    # Drop game 2 to keep the test focused.
    header_set["rowSet"] = [r for r in header_set["rowSet"] if r[1] == "0042500301"]
    line_set["rowSet"] = [r for r in line_set["rowSet"] if r[0] == "0042500301"]

    client = StubStatsClient(
        scoreboard=sb, boxscores={"0042500301": _default_boxscores()["0042500301"]}
    )

    result = fetch_yesterday_games(
        date(2026, 5, 14), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )

    assert isinstance(result, GamesDigest)
    game = result.games[0]
    assert "OT" in game.notable_events
    assert "(OT)" in game.score


def test_double_overtime_game_is_flagged_as_2ot(tmp_path: Path) -> None:
    sb = _load_scoreboard_fixture()
    header_set = sb["resultSets"][0]
    line_set = sb["resultSets"][1]
    _set_field(header_set, {"GAME_ID": "0042500301"}, "LIVE_PERIOD", 6)
    _set_field(line_set, {"GAME_ID": "0042500301"}, "LIVE_PERIOD", 6)
    header_set["rowSet"] = [r for r in header_set["rowSet"] if r[1] == "0042500301"]
    line_set["rowSet"] = [r for r in line_set["rowSet"] if r[0] == "0042500301"]

    client = StubStatsClient(
        scoreboard=sb, boxscores={"0042500301": _default_boxscores()["0042500301"]}
    )
    result = fetch_yesterday_games(
        date(2026, 5, 14), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )

    assert isinstance(result, GamesDigest)
    assert "2OT" in result.games[0].notable_events


def test_blowout_is_flagged_with_winner(tmp_path: Path) -> None:
    sb = _load_scoreboard_fixture()
    line_set = sb["resultSets"][1]
    # Make game 2 a 30-point Denver blowout.
    _set_field(line_set, {"GAME_ID": "0042500302", "TEAM_ABBREVIATION": "DEN"}, "PTS", 130)
    _set_field(line_set, {"GAME_ID": "0042500302", "TEAM_ABBREVIATION": "LAL"}, "PTS", 95)
    client = StubStatsClient(scoreboard=sb, boxscores=_default_boxscores())
    result = fetch_yesterday_games(
        date(2026, 5, 14), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )
    assert isinstance(result, GamesDigest)
    den_lal = next(g for g in result.games if g.game_id == "0042500302")
    assert any(e.startswith("BLOWOUT:DEN") for e in den_lal.notable_events)


def test_fouled_out_player_appears_in_notable_events(tmp_path: Path) -> None:
    boxscores = _default_boxscores()
    # Promote OG Anunoby's foul count to 6 (fouled out).
    bs = boxscores["0042500301"]
    headers = bs["resultSets"][0]["headers"]
    pf_idx = headers.index("PF")
    name_idx = headers.index("PLAYER_NAME")
    for row in bs["resultSets"][0]["rowSet"]:
        if row[name_idx] == "OG Anunoby":
            row[pf_idx] = 6

    sb = _load_scoreboard_fixture()
    sb["resultSets"][0]["rowSet"] = sb["resultSets"][0]["rowSet"][:1]
    sb["resultSets"][1]["rowSet"] = [
        row for row in sb["resultSets"][1]["rowSet"] if row[0] == "0042500301"
    ]

    client = StubStatsClient(scoreboard=sb, boxscores={"0042500301": bs})
    result = fetch_yesterday_games(
        date(2026, 5, 14), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )
    assert isinstance(result, GamesDigest)
    assert any(
        e == "FOULED_OUT:OG Anunoby" for e in result.games[0].notable_events
    )


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def test_second_call_for_same_date_is_a_cache_hit(tmp_path: Path) -> None:
    client = StubStatsClient(
        scoreboard=_load_scoreboard_fixture(), boxscores=_default_boxscores()
    )

    fetch_yesterday_games(
        date(2026, 5, 14), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )
    # Second call: cache files are present, so the client should not be hit.
    fetch_yesterday_games(
        date(2026, 5, 14), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )

    assert client.scoreboard_calls == 1
    assert len(client.boxscore_calls) == 2  # only from the first call


# ---------------------------------------------------------------------------
# Retry / error paths
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeHTTPError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"{status_code} server error")
        self.response = _FakeResponse(status_code)


def test_5xx_is_retried_with_backoff_and_eventually_succeeds(tmp_path: Path) -> None:
    sleeps: list[float] = []
    flaky = FlakyClient(
        fail_n=2, exc=_FakeHTTPError(503), then=_load_scoreboard_fixture()
    )

    # Patch boxscore fetch onto the flaky client by composing with the stub
    # for box-score happy path.
    class _Composed:
        def __init__(self, sb_client: FlakyClient) -> None:
            self._sb = sb_client
            self._bs = StubStatsClient(scoreboard={}, boxscores=_default_boxscores())

        def fetch_scoreboard(self, game_date: date) -> dict[str, Any]:
            return self._sb.fetch_scoreboard(game_date)

        def fetch_boxscore(self, game_id: str) -> dict[str, Any]:
            return self._bs.fetch_boxscore(game_id)

    composed = _Composed(flaky)

    result = fetch_yesterday_games(
        date(2026, 5, 14),
        client=composed,
        cache_dir=tmp_path,
        retry=RetryConfig(attempts=3, base_delay=1.0),
        sleep=sleeps.append,
    )

    assert isinstance(result, GamesDigest)
    assert flaky.scoreboard_calls == 3
    # Two sleeps between the three attempts: 1s, 2s (exponential).
    assert sleeps == [1.0, 2.0]


def test_total_5xx_failure_raises_typed_error(tmp_path: Path) -> None:
    flaky = FlakyClient(
        fail_n=99, exc=_FakeHTTPError(500), then=_load_scoreboard_fixture()
    )

    with pytest.raises(NBAStatsFetchError) as excinfo:
        fetch_yesterday_games(
            date(2026, 5, 14),
            client=flaky,
            cache_dir=tmp_path,
            retry=RetryConfig(attempts=3, base_delay=0.0),
            sleep=_no_sleep,
        )

    assert "scoreboard" in str(excinfo.value)
    assert flaky.scoreboard_calls == 3


def test_4xx_is_not_retried(tmp_path: Path) -> None:
    flaky = FlakyClient(
        fail_n=99, exc=_FakeHTTPError(404), then=_load_scoreboard_fixture()
    )
    with pytest.raises(NBAStatsFetchError):
        fetch_yesterday_games(
            date(2026, 5, 14),
            client=flaky,
            cache_dir=tmp_path,
            retry=RetryConfig(attempts=3, base_delay=0.0),
            sleep=_no_sleep,
        )
    # 404 is non-retryable; we should give up after the first attempt.
    assert flaky.scoreboard_calls == 1


def test_unexpected_response_shape_raises_parse_error(tmp_path: Path) -> None:
    client = StubStatsClient(
        scoreboard={"unexpected": "shape"},  # missing 'resultSets'
        boxscores={},
    )
    with pytest.raises(NBAStatsParseError):
        fetch_yesterday_games(
            date(2026, 5, 14),
            client=client,
            cache_dir=tmp_path,
            sleep=_no_sleep,
        )


def test_missing_player_stats_table_raises_parse_error(tmp_path: Path) -> None:
    sb = _load_scoreboard_fixture()
    sb["resultSets"][0]["rowSet"] = sb["resultSets"][0]["rowSet"][:1]
    sb["resultSets"][1]["rowSet"] = [
        row for row in sb["resultSets"][1]["rowSet"] if row[0] == "0042500301"
    ]
    # Boxscore is malformed — has no PlayerStats result set.
    bad_box = {"resultSets": [{"name": "TeamStats", "headers": [], "rowSet": []}]}
    client = StubStatsClient(scoreboard=sb, boxscores={"0042500301": bad_box})

    with pytest.raises(NBAStatsParseError):
        fetch_yesterday_games(
            date(2026, 5, 14),
            client=client,
            cache_dir=tmp_path,
            sleep=_no_sleep,
        )


def test_cache_dir_env_var_is_respected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NBA_MINI_CACHE_DIR", str(tmp_path / "envdir"))
    client = StubStatsClient(
        scoreboard=_load_scoreboard_fixture(), boxscores=_default_boxscores()
    )
    fetch_yesterday_games(date(2026, 5, 14), client=client, sleep=_no_sleep)
    cache_root = tmp_path / "envdir"
    # Scoreboard cache is league-namespaced so NBA/WNBA slates for the same
    # date don't collide.
    assert (cache_root / "scoreboard-nba-2026-05-14.json").exists()
    assert (cache_root / "boxscore-0042500301.json").exists()


# ---------------------------------------------------------------------------
# League selection
# ---------------------------------------------------------------------------


def test_league_ids_map_nba_and_wnba() -> None:
    assert LEAGUE_IDS["nba"] == "00"
    assert LEAGUE_IDS["wnba"] == "10"


def test_default_client_binds_league_id() -> None:
    assert NbaApiStatsClient("nba").league_id == "00"
    assert NbaApiStatsClient("wnba").league_id == "10"
    # Default is NBA for back-compat.
    assert NbaApiStatsClient().league_id == "00"


def test_scoreboard_cache_is_namespaced_by_league(tmp_path: Path) -> None:
    """NBA and WNBA slates for the same date must not collide in the cache."""
    nba_client = StubStatsClient(
        scoreboard=_load_scoreboard_fixture(), boxscores=_default_boxscores()
    )
    wnba_client = StubStatsClient(scoreboard=_empty_scoreboard(), boxscores={})

    nba = fetch_yesterday_games(
        date(2026, 5, 14), league="nba", client=nba_client,
        cache_dir=tmp_path, sleep=_no_sleep,
    )
    wnba = fetch_yesterday_games(
        date(2026, 5, 14), league="wnba", client=wnba_client,
        cache_dir=tmp_path, sleep=_no_sleep,
    )
    # Distinct files, distinct results — no cross-contamination.
    assert (tmp_path / "scoreboard-nba-2026-05-14.json").exists()
    assert (tmp_path / "scoreboard-wnba-2026-05-14.json").exists()
    assert isinstance(nba, GamesDigest)
    assert isinstance(wnba, NoGamesSignal)


# ---------------------------------------------------------------------------
# Most-recent-games search-back
# ---------------------------------------------------------------------------


class DateAwareStubClient:
    """Stub that has games only on specific dates — for search-back tests."""

    def __init__(self, *, game_dates: set[str], boxscores: dict[str, Any]) -> None:
        self.game_dates = game_dates
        self.boxscores = boxscores
        self.scoreboard_dates: list[str] = []

    def fetch_scoreboard(self, game_date: date) -> dict[str, Any]:
        iso = game_date.isoformat()
        self.scoreboard_dates.append(iso)
        if iso in self.game_dates:
            return copy.deepcopy(_load_scoreboard_fixture())
        return copy.deepcopy(_empty_scoreboard())

    def fetch_boxscore(self, game_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.boxscores[game_id])


def test_most_recent_returns_today_when_today_has_games(tmp_path: Path) -> None:
    client = DateAwareStubClient(
        game_dates={"2026-06-01"}, boxscores=_default_boxscores()
    )
    result = fetch_most_recent_games(
        date(2026, 6, 1), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )
    assert isinstance(result, GamesDigest)
    assert result.date == "2026-06-01"
    # Only probed the start date.
    assert client.scoreboard_dates == ["2026-06-01"]


def test_most_recent_walks_back_to_prior_game_day(tmp_path: Path) -> None:
    """Monday with no games walks back to Saturday's slate."""
    client = DateAwareStubClient(
        game_dates={"2026-05-30"}, boxscores=_default_boxscores()
    )
    result = fetch_most_recent_games(
        date(2026, 6, 1), client=client, cache_dir=tmp_path, sleep=_no_sleep
    )
    assert isinstance(result, GamesDigest)
    # Slate is dated to the day games were actually played.
    assert result.date == "2026-05-30"
    # Probed Mon (6/1), Sun (5/31), then found Sat (5/30).
    assert client.scoreboard_dates == ["2026-06-01", "2026-05-31", "2026-05-30"]


def test_most_recent_returns_no_games_when_window_is_empty(tmp_path: Path) -> None:
    client = DateAwareStubClient(game_dates=set(), boxscores={})
    result = fetch_most_recent_games(
        date(2026, 7, 4),
        client=client,
        cache_dir=tmp_path,
        retry=RetryConfig(),
        sleep=_no_sleep,
        max_lookback=3,
    )
    assert isinstance(result, NoGamesSignal)
    # Dated to the start date, not the last probed day.
    assert result.date == "2026-07-04"
    # Probed start + 3 lookback days = 4 dates.
    assert len(client.scoreboard_dates) == 4


# ---------------------------------------------------------------------------
# Multi-day recency window (fetch_recent_games)
# ---------------------------------------------------------------------------


def test_recent_games_merges_window_dated_to_most_recent(tmp_path: Path) -> None:
    # Games on the anchor day and one day inside the window: both slates merge,
    # and the digest is dated to the most recent (anchor) day.
    client = DateAwareStubClient(
        game_dates={"2026-06-01", "2026-05-31"}, boxscores=_default_boxscores()
    )
    result = fetch_recent_games(
        date(2026, 6, 1),
        window_days=3,
        client=client,
        cache_dir=tmp_path,
        sleep=_no_sleep,
    )
    assert isinstance(result, GamesDigest)
    assert result.date == "2026-06-01"
    # Two slates' games are pooled (the fixture's games appear once per day).
    single = fetch_most_recent_games(
        date(2026, 6, 1),
        client=DateAwareStubClient(
            game_dates={"2026-06-01"}, boxscores=_default_boxscores()
        ),
        cache_dir=tmp_path,
        sleep=_no_sleep,
    )
    assert isinstance(single, GamesDigest)
    assert len(result.games) == 2 * len(single.games)


def test_recent_games_skips_quiet_days_inside_window(tmp_path: Path) -> None:
    # Anchor has games; the day before is quiet; two days before has games.
    # The quiet day is skipped, not treated as the end of the walk.
    client = DateAwareStubClient(
        game_dates={"2026-06-01", "2026-05-30"}, boxscores=_default_boxscores()
    )
    result = fetch_recent_games(
        date(2026, 6, 1),
        window_days=3,
        client=client,
        cache_dir=tmp_path,
        sleep=_no_sleep,
    )
    assert isinstance(result, GamesDigest)
    assert result.date == "2026-06-01"
    # 06-01 (anchor) + 05-30 both contribute; 05-31 (quiet) contributes nothing.
    assert len(result.games) > 0


def test_recent_games_no_games_in_window(tmp_path: Path) -> None:
    client = DateAwareStubClient(game_dates=set(), boxscores={})
    result = fetch_recent_games(
        date(2026, 7, 4),
        window_days=3,
        client=client,
        cache_dir=tmp_path,
        sleep=_no_sleep,
        max_lookback=3,
    )
    assert isinstance(result, NoGamesSignal)
    assert result.date == "2026-07-04"
