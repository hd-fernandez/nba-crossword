# pipeline

Python package that generates the daily NBA Mini puzzle. Runs locally for development and on GitHub Actions in production.

## Local dev

Requires [uv](https://github.com/astral-sh/uv) and Python 3.12+.

```bash
cd pipeline
uv sync --extra dev
uv run pytest
```

## Layout

- `nba_mini/ingest/` — Reddit and nba.com fetchers
- `nba_mini/grid.py` — 5x5 fill algorithm (deterministic)
- `nba_mini/clues.py` — Claude Sonnet clue generation in three voices
- `nba_mini/schema.py` — pydantic models for the puzzle JSON contract
- `nba_mini/generate.py` — CLI orchestrator (entry point)
- `nba_mini/season_context.md` — hand-maintained calendar-phase snippet
- `tests/` — pytest suite with recorded fixtures
