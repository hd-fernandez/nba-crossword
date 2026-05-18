---
title: "feat: NBA Mini v0 — daily puzzle PWA + automated generation pipeline"
type: feat
status: active
date: 2026-05-17
origin: context-engineering/brainstorms/2026-05-15-nyt-nba-crossword-design.md
---

# feat: NBA Mini v0 — daily puzzle PWA + automated generation pipeline

## Summary

Ship a PWA that serves a daily 5×5 NBA mini crossword, generated end-to-end by an automated pipeline that runs on GitHub Actions every morning. v0 ingests yesterday's r/nba discourse and nba.com box scores, drafts a single puzzle with Claude Sonnet, and commits it to the repo as a static JSON file. The frontend fetches today's puzzle, lets the user solve it with timer + reveals, shows a NYT/Wordle-style finish screen with a spoiler-free emoji share, and tracks streaks in `localStorage`. No accounts, no push, no LLM judge — those are v0.5/v1 problems.

---

## Problem Frame

The brainstorm (see origin) committed to a fully automated content engine for a side project. v0's job is to make the engine real end-to-end on the cheapest, simplest stack possible — proving that the daily pipeline can ship a publishable puzzle every morning without a human in the loop. Quality compounding, candidate ranking, push, and accounts are explicitly deferred. The risk we are de-risking in v0 is *can the pipeline actually produce something playable every day*, not *is it the best possible puzzle*.

---

## Requirements

- R1. A daily 5×5 crossword puzzle is generated automatically every morning when there were NBA games the previous calendar day.
- R2. Generation pipeline ingests two sources: yesterday's r/nba discourse (top posts/comments, game threads, post-game threads) and yesterday's nba.com box scores.
- R3. A weekly-refreshed "season context" snippet is prepended to the clue-writing prompt so clues are framed correctly for the current calendar phase (currently 2026 Conference Semis).
- R4. Clue voice mix targets 50% wry-NYT / 30% online-discoursey / 20% factual across each puzzle.
- R5. The puzzle is published as a static JSON file at a deterministic path, fetched by the frontend.
- R6. On no-game days, no puzzle is generated; the frontend shows a "no puzzle today" state and streaks skip (do not break).
- R7. The PWA renders the grid, supports keyboard + touch input, shows a toggleable timer, supports NYT-style reveals (letter/word/puzzle) with revealed cells tracked, and shows a finish screen with time, streak, and a Wordle-style spoiler-free emoji share.
- R8. Streaks are tracked in `localStorage`. Completion = streak day. Off-days skip. No grace mechanic.
- R9. The whole stack costs ≤ ~$10/month at side-project scale and runs unattended.

**Origin acceptance examples (carried from brainstorm):**

- AE1. *"If you read r/nba yesterday, you'll get this puzzle."* — clues anchor in yesterday's discourse, not historical trivia.
- AE2. A 40-point game in May reads as a *playoff* 40-point game in the clue, because season context is in scope.
- AE3. The day after the Finals end (no games yesterday), the app shows a dormant state and streaks do not break.

---

## Scope Boundaries

- No native iOS or Android app
- No push notifications (web or native)
- No user accounts; no cloud-synced state
- No LLM-as-judge / candidate ranking pipeline (deferred to v0.5)
- No leaderboards, friend graphs, or share-time competitions
- No X/Twitter ingestion
- No archive / play-old-puzzles mode
- No Sunday extended puzzle or themed marquee puzzles
- No paid subscription tier
- No reveal-aware emoji rendering beyond a single "revealed" indicator (full color spectrum 🟩/🟨/🟧 left for v0.5 polish)

### Deferred to Follow-Up Work

- LLM-as-judge ranking N candidate puzzles per night → v0.5
- Rate-and-rank capture loop (Henry rates A/B/C with one-line reason → few-shot retraining) → v0.5
- Native iOS / push / accounts → v1
- X/Twitter source → v1+ if material is missing

---

## Context & Research

### Relevant Code and Patterns

This is a greenfield repo. The only existing artifacts are:

- [README.md](../../README.md) — placeholder
- [CLAUDE.md](../../CLAUDE.md) — project instructions, CE folder overrides
- [context-engineering/brainstorms/2026-05-15-nyt-nba-crossword-design.md](../brainstorms/2026-05-15-nyt-nba-crossword-design.md) — origin document
- [context-engineering/brainstorms/mockups/index.html](../brainstorms/mockups/index.html) — visual companion, can inform initial frontend styling

No existing patterns to follow. The plan establishes them.

### Institutional Learnings

`context-engineering/solutions/` is empty. As patterns emerge during v0 (e.g., reliable nba.com fetch shape, prompt structures that produce good clues), `ce-compound` should write learnings here.

### External References

External research deferred to implementation — the choices below are conventional defaults, not novel territory:

- `nba_api` Python package (`swar/nba_api`) is the de-facto standard for nba.com stats endpoints. Worth confirming current maintenance state at implementation time but is the v0 primary.
- Reddit JSON API (`https://www.reddit.com/r/nba/<feed>.json`) is free with a `User-Agent` header; auth needed only for higher rate limits. Confirm current 2026 terms at implementation time.
- Next.js 14+ App Router + Vercel deploy is the standard PWA path. Manifest + service worker required for "Add to Home Screen."
- Anthropic SDK (`@anthropic-ai/sdk` for TS, `anthropic` for Python) — pipeline is Python (lives near data tooling), frontend has no LLM calls.

---

## Key Technical Decisions

- **Pipeline language: Python.** The data layer (Reddit, nba.com, scraping fallbacks) has the strongest ecosystem in Python. Frontend is TypeScript; the two systems only communicate via the daily JSON file. Rationale: minimize friction, use the right tool per layer.
- **Frontend: Next.js 14 (App Router) on Vercel.** PWA support is solid, deploy is one git push, ecosystem covers everything we need now and in v1. Origin doc decision.
- **Puzzle storage: static JSON committed to `puzzles/YYYY-MM-DD.json` in the repo.** No DB, no API. Frontend fetches from public path. Rationale: the puzzle *is* a daily artifact; git becomes the audit log. Cost = $0.
- **User state: `localStorage` only.** No accounts in v0. Streaks, completion, settings live in browser. Rationale: origin doc decision; sidesteps auth + DB entirely.
- **Generation orchestration: GitHub Actions cron at 06:00 ET (~10:00/11:00 UTC).** Free for public repos, dead simple, commits the new puzzle JSON via the workflow's GITHUB_TOKEN. Rationale: origin doc decision.
- **LLM provider: Claude Sonnet for generation (clue writing).** v0 uses one model only — Opus + judge step is v0.5. Rationale: cost-efficient at puzzle volume, sufficient quality for v0 single-shot generation.
- **Grid construction: rule-based fill with LLM-assisted answer selection (not a full LLM-driven fill).** A 5×5 grid has tractable combinatorics; brute-force constraint satisfaction with a wordlist is well-understood. The LLM picks the *answer pool* from yesterday's discourse, the fill algorithm places them. Rationale: LLM-driven fill is unreliable for crossword constraints; deterministic fill with curated answers gives predictable results.
- **No Reddit OAuth in v0.** Use the unauthenticated JSON endpoints with a clear `User-Agent`. Rate limits are fine for a single daily fetch. Rationale: cost + setup minimization.
- **Season context: hand-maintained markdown file, refreshed manually.** `pipeline/season_context.md` is a few paragraphs describing the current phase. v0.5 can automate refresh. Rationale: origin doc decision; trivial to maintain weekly.
- **Reveal tracking: a single boolean per cell (`revealed: bool`) with a single emoji (🟨) in the share grid.** Origin doc allowed for tiered emoji (clean / letter / word) — explicitly deferred to v0.5 polish to keep v0 simple.

---

## Open Questions

### Resolved During Planning

- *Should v0 ship the LLM judge?* — No. v0 generates one puzzle and ships. v0.5 introduces N candidates + judge. (Confirmed with user.)
- *Where do plans live?* — `context-engineering/plans/` per repo CLAUDE.md override.

### Deferred to Implementation

- *Exact `nba_api` endpoints to call.* Determined when first hitting the API.
- *Reddit fetch shape — old.reddit JSON vs www.reddit JSON.* The www endpoint has historically required more headers; pick at implementation.
- *Wordlist source for the fill algorithm.* Public crossword wordlists exist (e.g., XWordInfo data, Peter Broda's wordlist). Choose at implementation; could also start with a tiny custom NBA-skewed list and grow.
- *Exact prompt shape for clue generation.* Will iterate; v0 ships with a workable v1 prompt and tunes from there.
- *PWA service worker strategy* — what to cache, offline behavior. Pick at frontend implementation.
- *GitHub Actions concurrency / retry.* Sensible defaults at implementation; the workflow can be re-run manually if it fails.

---

## Output Structure

```
nba-crossword/
├── pipeline/                       # Python: daily puzzle generation
│   ├── pyproject.toml              # uv / poetry-managed Python package
│   ├── nba_mini/
│   │   ├── __init__.py
│   │   ├── ingest/
│   │   │   ├── reddit.py           # r/nba fetch + extraction
│   │   │   └── nba_stats.py        # nba.com box scores via nba_api
│   │   ├── season_context.md       # hand-maintained snippet
│   │   ├── generate.py             # main entry point (CLI)
│   │   ├── grid.py                 # 5x5 fill algorithm
│   │   ├── clues.py                # Claude Sonnet clue generation
│   │   └── schema.py               # puzzle JSON schema (pydantic)
│   └── tests/
│       ├── test_ingest_reddit.py
│       ├── test_ingest_nba_stats.py
│       ├── test_grid.py
│       ├── test_clues.py
│       └── fixtures/               # recorded API responses
├── web/                            # Next.js PWA
│   ├── package.json
│   ├── next.config.mjs
│   ├── public/
│   │   ├── manifest.webmanifest
│   │   └── puzzles/                # symlink or copy of /puzzles at build
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                # today's puzzle
│   │   └── api/                    # (none in v0; static fetch only)
│   ├── components/
│   │   ├── Grid.tsx
│   │   ├── ClueBar.tsx
│   │   ├── Timer.tsx
│   │   ├── FinishScreen.tsx
│   │   ├── Share.tsx
│   │   └── StreakBadge.tsx
│   ├── lib/
│   │   ├── storage.ts              # localStorage helpers (streak, completion, settings)
│   │   ├── puzzle.ts               # fetch + parse today's puzzle
│   │   └── share.ts                # emoji grid generation
│   └── tests/
│       ├── grid.test.tsx
│       ├── share.test.ts
│       └── storage.test.ts
├── puzzles/                        # daily JSON, committed by GH Actions
│   └── YYYY-MM-DD.json             # generated daily; .gitkeep at start
└── .github/
    └── workflows/
        └── daily-puzzle.yml        # cron: 06:00 ET
```

The implementer may adjust this layout if implementation reveals a better one. Per-unit `**Files:**` lists are authoritative.

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Actions (06:00 ET daily)                                │
│                                                                 │
│   ┌────────────┐   ┌────────────┐   ┌────────────┐              │
│   │  reddit.py │   │nba_stats.py│   │season_     │              │
│   │  (yest.    │   │  (yest.    │   │context.md  │              │
│   │   posts)   │   │   games)   │   │  (weekly)  │              │
│   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘              │
│         └─────────────┬──┴──────────────────┘                   │
│                       ▼                                         │
│                ┌─────────────┐                                  │
│                │ generate.py │  guard: yesterday had games?     │
│                │             │  if no → exit clean, no commit   │
│                └─────┬───────┘                                  │
│                      ▼                                          │
│              ┌──────────────┐                                   │
│              │  grid.py     │  pick ~5–7 answers from raw       │
│              │  (fill 5×5)  │  ingest material; deterministic   │
│              └──────┬───────┘  fill against wordlist            │
│                     ▼                                           │
│              ┌──────────────┐                                   │
│              │  clues.py    │  for each entry: prompt Sonnet    │
│              │  (Sonnet)    │  with season ctx + 3 voice modes; │
│              └──────┬───────┘  emit clue with voice tag         │
│                     ▼                                           │
│           ┌──────────────────┐                                  │
│           │ puzzles/         │  validate against schema         │
│           │ YYYY-MM-DD.json  │  git add + commit + push         │
│           └────────┬─────────┘                                  │
└────────────────────┼────────────────────────────────────────────┘
                     ▼
            ┌─────────────────┐         ┌──────────────┐
            │  Vercel (PWA)   │ ←fetch─ │  user phone  │
            │  Next.js App    │         │  / browser   │
            └─────────────────┘         └──────────────┘
```

**Puzzle JSON schema (illustrative):**

```
{
  "date": "2026-05-15",
  "grid": {
    "size": 5,
    "cells": [ [{"answer": "L"} | {"block": true}, ...], ... ]
  },
  "entries": [
    {
      "id": "1A",
      "direction": "across",
      "row": 0,
      "col": 0,
      "answer": "LEBRON",
      "clue": "Visited TD Garden, scored 40, left.",
      "voice": "wry"
    }
  ],
  "season_context_version": "2026-05-12",
  "generated_at": "2026-05-17T10:03:14Z",
  "model": "claude-sonnet-4-5"
}
```

---

## Implementation Units

- U1. **Repo skeleton: pipeline + web monorepo layout**

**Goal:** Establish the directory structure for the Python pipeline and the Next.js web app side-by-side in the existing repo. No business logic yet.

**Requirements:** R5, R9

**Dependencies:** None

**Files:**
- Create: `pipeline/pyproject.toml`
- Create: `pipeline/nba_mini/__init__.py`
- Create: `web/package.json`
- Create: `web/next.config.mjs`
- Create: `web/app/layout.tsx`, `web/app/page.tsx` (placeholder content)
- Create: `puzzles/.gitkeep`
- Modify: `.gitignore` (add `node_modules/`, `.next/`, `dist/`, `__pycache__/`, `.venv/`)
- Modify: `README.md` (add brief "pipeline/" and "web/" section)

**Approach:**
- Python tool: prefer `uv` (fast, reproducible) but `poetry` is fine. Pick one and document.
- Next.js: scaffold via `create-next-app@latest` then trim to App Router + TypeScript only.
- Keep both deployable independently — no top-level package manager that owns both.

**Patterns to follow:** None (greenfield).

**Test scenarios:** Test expectation: none — pure scaffolding, no behavior.

**Verification:**
- `cd pipeline && python -c "import nba_mini"` succeeds
- `cd web && npm run dev` boots Next.js on localhost
- `git status` shows no ignored junk

---

- U2. **Puzzle JSON schema (canonical contract between pipeline and frontend)**

**Goal:** Define the puzzle JSON shape once, in code, in both languages. This is the contract that lets pipeline and frontend evolve independently.

**Requirements:** R5

**Dependencies:** U1

**Files:**
- Create: `pipeline/nba_mini/schema.py` — pydantic models (`Puzzle`, `Entry`, `Cell`)
- Create: `web/lib/puzzle.ts` — TypeScript types + zod (or similar) parser
- Create: `puzzles/example.json` — a hand-crafted reference puzzle for testing both ends
- Create: `pipeline/tests/test_schema.py`
- Create: `web/tests/puzzle.test.ts`

**Approach:**
- Schema fields: `date` (ISO), `grid.size`, `grid.cells[][]` (each cell is `{answer: char}` or `{block: true}`), `entries[]` (each: `id`, `direction: across|down`, `row`, `col`, `answer`, `clue`, `voice: wry|discoursey|factual`, `revealed_default: false`), `season_context_version`, `generated_at`, `model`.
- Same field names in both languages. No abbreviations.
- Validation rules: grid is 5×5; every entry's answer letters match the grid cells they cover; every non-block cell belongs to exactly one across and one down entry.

**Patterns to follow:** Pydantic v2 conventions on the Python side; zod runtime parsing on the TypeScript side.

**Test scenarios:**
- Happy path: parsing `puzzles/example.json` succeeds in both Python and TypeScript.
- Edge case: a non-5×5 grid is rejected.
- Edge case: an entry whose `answer` does not match the grid letters is rejected.
- Edge case: a cell with both `answer` and `block: true` is rejected.
- Error path: missing required field returns a clear validation error.

**Verification:**
- `pytest pipeline/tests/test_schema.py` passes
- `npm test -- puzzle.test.ts` passes
- `puzzles/example.json` round-trips through both validators

---

- U3. **Reddit ingest — yesterday's r/nba**

**Goal:** Fetch yesterday's top posts (and top-N comments per post) from r/nba and return a structured "discourse digest" the generator can consume.

**Requirements:** R2

**Dependencies:** U1

**Files:**
- Create: `pipeline/nba_mini/ingest/reddit.py`
- Create: `pipeline/tests/test_ingest_reddit.py`
- Create: `pipeline/tests/fixtures/reddit_top_posts.json` (recorded response)

**Approach:**
- Single function: `fetch_yesterday_discourse(date: date) -> RedditDigest`
- Return shape: list of post objects with `title`, `flair`, `score`, `comment_count`, `top_comments: list[str]`, `permalink`.
- Use `https://www.reddit.com/r/nba/top.json?t=day` as the base feed; filter by `created_utc` to "yesterday" (US/Eastern day boundary).
- Pull top-N (probably 5–10) comments per post via the `<permalink>.json` endpoint.
- Standard `User-Agent` header. Add a short `time.sleep` between calls to be polite.
- Cache the fetch to disk per-date so reruns during dev don't hammer the API.

**Patterns to follow:** None yet; this *is* the pattern.

**Test scenarios:**
- Happy path: given a recorded fixture, the function returns the expected number of posts and comments.
- Edge case: a post from two days ago in the feed is excluded by the date filter.
- Edge case: a removed/deleted comment is skipped, not crashed on.
- Error path: 429 (rate limit) is retried with backoff a small number of times before giving up cleanly.
- Error path: network error returns a typed exception, not a raw `requests` error.

**Verification:**
- `pytest pipeline/tests/test_ingest_reddit.py` passes
- Manual run against live Reddit returns plausible "yesterday" data

---

- U4. **NBA stats ingest — yesterday's box scores**

**Goal:** Fetch yesterday's NBA games (box scores, key events) and return a structured "games digest" the generator can consume. Also surface the *no-games* signal (R6).

**Requirements:** R2, R6

**Dependencies:** U1

**Files:**
- Create: `pipeline/nba_mini/ingest/nba_stats.py`
- Create: `pipeline/tests/test_ingest_nba_stats.py`
- Create: `pipeline/tests/fixtures/nba_stats_scoreboard.json`
- Modify: `pipeline/pyproject.toml` (add `nba_api` dep; basketball-reference scraping is fallback only)

**Approach:**
- Function: `fetch_yesterday_games(date: date) -> GamesDigest | NoGamesSignal`
- `GamesDigest` carries: list of games with `home`, `away`, `score`, `top_performers` (player + line), `notable_events` (ejections, technicals, OT, blowouts, buzzer-beaters when computable from box score).
- Use `nba_api.stats.endpoints.scoreboardv2` for the date, then per-game `boxscoretraditionalv2` for player lines.
- Determine "yesterday" in US/Eastern. NBA's official day boundary lines up with ET.
- If `scoreboardv2` returns zero games for the date, return `NoGamesSignal` — the caller decides what to do.
- Cache responses to disk per-date.

**Patterns to follow:** Reddit ingest pattern (U3) — same caching shape, same error handling.

**Test scenarios:**
- Happy path: a normal slate (e.g., 8-game Tuesday) returns the expected number of games with top performers populated.
- Happy path: a single-game playoff night returns one game.
- Edge case: a no-games day returns `NoGamesSignal`, not an empty `GamesDigest`.
- Edge case: an OT game is flagged as such in `notable_events`.
- Edge case: an ejection (player with very low minutes + technical) is flagged in `notable_events` if box score signals are sufficient; otherwise it is OK to miss it (Reddit will catch it).
- Error path: nba.com 5xx is retried with backoff; total failure raises a typed exception.
- Error path: an unexpected response shape (API change) is caught and wrapped, not silently parsed wrong.

**Verification:**
- `pytest pipeline/tests/test_ingest_nba_stats.py` passes
- Manual run against a recent date returns plausible games

---

- U5. **Season context (hand-maintained snippet)**

**Goal:** A small markdown file containing the current calendar phase + live storylines, loaded at generation time and prepended to the clue prompt.

**Requirements:** R3

**Dependencies:** U1

**Files:**
- Create: `pipeline/nba_mini/season_context.md` — initial content for May 2026 (Conference Semis, post-Lottery, Wemby's first ejection still recent)
- Create: `pipeline/nba_mini/season_context.py` — loader + version tag (file mtime or content hash)
- Create: `pipeline/tests/test_season_context.py`

**Approach:**
- Loader returns `(text: str, version: str)`.
- `version` is a content hash (sha256, first 8 chars) so the puzzle JSON can record which season-context version it was built against. Lets us reason later about clue-tone changes.
- File is markdown but the loader returns plaintext; markdown is for human authoring only.

**Patterns to follow:** None; trivial.

**Test scenarios:**
- Happy path: loader returns non-empty text and a stable version hash for unchanged content.
- Edge case: editing the file changes the version hash.
- Error path: a missing file raises a clear error (don't generate a puzzle without season context).

**Verification:**
- `pytest pipeline/tests/test_season_context.py` passes

---

- U6. **5×5 grid fill algorithm**

**Goal:** Given a pool of candidate "must-include" answers (with their NBA flavor) plus a wordlist, produce a valid 5×5 crossword grid with all entries filled. Deterministic; no LLM in this loop.

**Requirements:** R7 (the grid must be valid for the frontend to render)

**Dependencies:** U2 (schema)

**Files:**
- Create: `pipeline/nba_mini/grid.py`
- Create: `pipeline/nba_mini/wordlist.py` — wordlist loader
- Create: `pipeline/data/wordlist.txt` — initial wordlist (TBD source; can start with a small NBA-skewed seed plus standard crossword fill)
- Create: `pipeline/tests/test_grid.py`

**Approach:**
- Function: `fill_grid(candidate_answers: list[str], wordlist: list[str], black_squares: int = 4) -> Grid`.
- Standard mini-crossword constraints: 5×5, 4–6 black squares typical, every white cell belongs to one across + one down.
- Algorithm: pick a black-square pattern (small set of canonical NYT-mini-style patterns), then constraint-satisfaction fill — try to seat candidate answers first, fill the rest from the wordlist. Backtrack on dead ends.
- If no fill is possible with the candidates as required, gracefully relax: drop the lowest-priority candidate and retry. Log which candidates dropped out.
- Determinism: take a `seed: int = 0` parameter so the same inputs produce the same output. Daily seed = `int(date.toordinal())`.

**Patterns to follow:** Standard backtracking constraint satisfaction. Reference open-source mini-fillers for inspiration (deferred to implementation — `qxw`, `phil`, etc.).

**Test scenarios:**
- Happy path: given a candidate pool that fits trivially (e.g., one 5-letter word and standard fill), returns a valid grid.
- Happy path: with a fixed seed, two runs produce the same grid.
- Edge case: an over-constrained input (six 5-letter words, no compatible crossings) gracefully drops candidates and still returns a valid grid.
- Edge case: with a deliberately tiny wordlist, the function reports failure rather than infinite-looping.
- Error path: an answer in the candidate pool that contains non-letter characters is rejected with a clear error.
- Integration: the grid this unit produces validates clean against U2's schema.

**Verification:**
- `pytest pipeline/tests/test_grid.py` passes
- 100 randomly-seeded runs all produce schema-valid grids in <2s each

---

- U7. **Clue generation with Claude Sonnet — three voices**

**Goal:** For each entry in a filled grid, generate a clue in the appropriate voice (wry / discoursey / factual), using the season context + the relevant slice of yesterday's discourse + box score.

**Requirements:** R3, R4

**Dependencies:** U2, U3, U4, U5, U6

**Files:**
- Create: `pipeline/nba_mini/clues.py`
- Create: `pipeline/nba_mini/prompts/clue_wry.md`
- Create: `pipeline/nba_mini/prompts/clue_discoursey.md`
- Create: `pipeline/nba_mini/prompts/clue_factual.md`
- Create: `pipeline/tests/test_clues.py`
- Modify: `pipeline/pyproject.toml` (add `anthropic` dep)

**Approach:**
- Function: `generate_clues(entries: list[Entry], context: GenerationContext) -> list[Entry]` — entries go in without `clue`, come out with `clue` and `voice` set.
- Voice assignment per puzzle: target distribution 50/30/20 (wry/discoursey/factual). For a 5×5 with ~6–8 entries, that means roughly 3–4 wry, 2 discoursey, 1–2 factual. Round to integers; small drift is fine.
- For each entry: prompt Sonnet with `(season_context, yesterday_discourse, target_voice, answer, optional grounding fact)`. The model returns one clue.
- Each prompt file is markdown with the voice's specific style guidance + 2–3 in-prompt few-shot examples (which we can grow over time).
- Validation on the model output: clue fits length budget (<=80 chars suggested), doesn't contain the answer literally, doesn't reveal the answer via obvious substring.
- On validation failure: retry up to N times with a "your previous clue did X — fix it" follow-up. After N tries, fall back to a templated factual clue ("[Player] [factual line from box score]") so we never block puzzle shipment.

**Patterns to follow:** Prompts as markdown files (not inline strings) so we can iterate without code changes. Same pattern most prompt-engineering work uses.

**Test scenarios:**
- Happy path: with mocked Anthropic responses, every entry comes back with a non-empty clue and a voice tag.
- Happy path: the voice distribution across a 6-entry puzzle approximates 50/30/20 (e.g., 3 wry / 2 discoursey / 1 factual).
- Edge case: a model response that contains the answer is rejected and retried.
- Edge case: a model response longer than the length budget is rejected and retried.
- Error path: persistent retry failure falls back to a templated factual clue, doesn't crash the pipeline.
- Error path: Anthropic API outage raises a typed pipeline error after retries.
- Integration: a full 6-entry puzzle's clues all validate against U2's schema.

**Verification:**
- `pytest pipeline/tests/test_clues.py` passes
- A manual generate run produces clues that pass spot-check against the brainstorm's voice examples

---

- U8. **End-to-end generator: `generate.py` orchestrator**

**Goal:** The CLI entry point that runs the whole pipeline for a given date and writes `puzzles/YYYY-MM-DD.json`.

**Requirements:** R1, R5, R6

**Dependencies:** U2, U3, U4, U5, U6, U7

**Files:**
- Create: `pipeline/nba_mini/generate.py` (with `if __name__ == "__main__": main()`)
- Create: `pipeline/tests/test_generate_e2e.py`

**Approach:**
- CLI: `python -m nba_mini.generate --date 2026-05-16 [--dry-run] [--out puzzles/]`
- Default date: yesterday in US/Eastern.
- Order of operations:
  1. Load season context (U5)
  2. Fetch nba.com games (U4) — if `NoGamesSignal`, log and exit cleanly with code 0; **no JSON written, no commit needed**.
  3. Fetch r/nba discourse (U3)
  4. Pick candidate answer pool (LLM-assisted: prompt Sonnet with the digest, ask for ~7 candidate answers across players/teams/words/moments). This is *answer selection*, not clue writing.
  5. Fill grid (U6) with those candidates
  6. Generate clues (U7)
  7. Validate full puzzle against schema (U2)
  8. Write to `puzzles/<date>.json`
- `--dry-run` skips the file write and prints the JSON to stdout.
- Idempotency: if `puzzles/<date>.json` already exists, exit cleanly (code 0) unless `--force` is passed. The cron job is therefore safe to re-run.

**Execution note:** Heavy reliance on lower units — recommend writing the e2e test (U8's `test_generate_e2e.py`) early with the lower units mocked, so the orchestrator's flow is exercised before all dependencies are real.

**Patterns to follow:** Each unit's I/O contract becomes a clean seam in this orchestrator.

**Test scenarios:**
- Covers AE3. No-games day → process exits 0, no JSON written.
- Happy path: with all dependencies mocked, a full game day produces a schema-valid `puzzles/<date>.json`.
- Happy path: passing `--date 2026-05-15` and re-running with the same date is a no-op (idempotency).
- Edge case: `--force` overwrites an existing puzzle file.
- Error path: any one failing dependency (Reddit down, nba.com down, Anthropic down) raises a typed error and exits non-zero — pipeline should *fail loud* rather than ship a half-baked puzzle.
- Integration: a real (non-mocked) end-to-end run, gated behind an env var so it doesn't hit live APIs in CI, produces a plausible puzzle for a known good date.

**Verification:**
- `pytest pipeline/tests/test_generate_e2e.py` passes
- Manual e2e run for a recent date produces a valid puzzle file
- Manual no-games-day run exits clean with no file written

---

- U9. **GitHub Actions daily cron**

**Goal:** Every morning at ~06:00 ET, the pipeline runs in CI and commits the day's puzzle JSON to `main`.

**Requirements:** R1, R6, R9

**Dependencies:** U8

**Files:**
- Create: `.github/workflows/daily-puzzle.yml`
- Modify: `pipeline/pyproject.toml` (lock dep versions)

**Approach:**
- Trigger: `schedule: cron: "0 10 * * *"` (10:00 UTC = 06:00 ET in summer; will drift in winter — acceptable for v0).
- Also `workflow_dispatch` so we can manually run for any date.
- Steps: checkout → set up Python (uv) → install pipeline → run `python -m nba_mini.generate` → if file written, `git add puzzles/ && git commit && git push`.
- If `generate.py` exits 0 with no file (no-games day), the commit step is skipped (check `git status --porcelain puzzles/`).
- Secrets: `ANTHROPIC_API_KEY` in GH Secrets. No other secrets needed in v0.
- Concurrency: `concurrency: daily-puzzle` so a manual trigger doesn't race the cron.

**Patterns to follow:** Standard GH Actions cron + commit-back pattern. Use `actions/checkout@v4` with `persist-credentials: true`; use the workflow's GITHUB_TOKEN for the push.

**Test scenarios:**
- Test expectation: limited (CI workflows are awkward to unit-test) — but include:
  - A `workflow_dispatch` smoke run on a known good past date that produces a puzzle artifact.
  - A `workflow_dispatch` smoke run on a known no-games date that exits clean with no commit.
  - Confirm secret loading works (a run that fails on missing key is the negative test).

**Verification:**
- A `workflow_dispatch` run for a past game day commits a valid puzzle JSON
- A `workflow_dispatch` run for a no-games day exits clean with no commit
- The scheduled cron fires and produces a puzzle the morning after the next NBA game day

---

- U10. **Frontend: grid + interaction (no clue voice yet, no finish screen)**

**Goal:** A working 5×5 grid component that fetches today's puzzle JSON, supports keyboard + touch input, and shows clues as you move the cursor.

**Requirements:** R5, R7

**Dependencies:** U2

**Files:**
- Create: `web/components/Grid.tsx`
- Create: `web/components/ClueBar.tsx`
- Create: `web/lib/puzzle.ts` (already created in U2 — extend with fetch helper)
- Create: `web/lib/state.ts` — local solve state (current selection, entered letters, direction)
- Modify: `web/app/page.tsx` — fetch today's puzzle and render `<Grid>` + `<ClueBar>`
- Create: `web/tests/grid.test.tsx`

**Approach:**
- Solve state is a React reducer or a small Zustand store; local-only, not persisted yet.
- Today's puzzle: fetch `/puzzles/<today>.json`. If 404 (no puzzle today), render a "no puzzle today — there were no NBA games yesterday" state.
- Grid renders cells, with the active cell + active entry highlighted (per mockup).
- Keyboard handling: arrow keys move, letter keys enter, backspace deletes & moves back, space toggles direction (across↔down), tab moves to next entry.
- Touch: tap a cell to select; tap again to flip direction. Visible numbers on cells that start an entry.

**Patterns to follow:** The visual companion at [context-engineering/brainstorms/mockups/index.html](../brainstorms/mockups/index.html) for layout + colors.

**Test scenarios:**
- Happy path: rendering a valid puzzle JSON shows a 5×5 grid with the right black squares and entry numbers.
- Happy path: typing a letter moves the cursor; backspace moves back.
- Happy path: tab cycles through entries.
- Edge case: a 404 on the fetch shows the "no puzzle today" state.
- Edge case: clicking a black square is a no-op.
- Integration: with a real `puzzles/example.json`, the grid renders and accepts input.

**Verification:**
- `npm test` (web) passes
- `npm run dev` shows the grid solving an example puzzle
- Lighthouse smoke shows interactive in <1s on a fast connection

---

- U11. **Frontend: timer, reveals, finish screen, share**

**Goal:** Wrap up the solve experience — toggleable timer, reveal letter/word/puzzle, finish screen with time + Wordle-style spoiler-free emoji share.

**Requirements:** R7

**Dependencies:** U10

**Files:**
- Create: `web/components/Timer.tsx`
- Create: `web/components/FinishScreen.tsx`
- Create: `web/components/Share.tsx`
- Create: `web/lib/share.ts` — emoji grid generator
- Modify: `web/components/Grid.tsx` — add reveal-tracking; revealed cells get a flag
- Modify: `web/lib/state.ts` — track elapsed time and revealed cells
- Create: `web/tests/share.test.ts`
- Create: `web/tests/finish.test.tsx`

**Approach:**
- Timer: starts on first input; pauses on tab blur; visible by default with a settings toggle to hide. Hidden timer still records elapsed.
- Reveals: a small "reveal" menu (letter / word / puzzle). Revealed cells set `revealed: true` in state and render slightly differently (subtle indicator). Reveals do not invalidate the solve.
- Finish detection: every cell filled correctly → trigger finish screen.
- Finish screen: confetti, time, streak count (from U12), share button.
- Share: a 5×5 emoji grid where 🟩 = clean cell, 🟨 = revealed cell, plus a tagline `nbamini.app · MMM D · 1:24`. No date-specific spoilers, no answer reveals.
- Web Share API (`navigator.share`) with clipboard fallback.

**Patterns to follow:** NYT mini and Wordle for share text formatting.

**Test scenarios:**
- Covers AE1 / AE3 indirectly through finish-screen experience; covers R7 directly.
- Happy path: solving without any reveals produces a share grid that is all 🟩.
- Happy path: revealing one letter produces a share grid with one 🟨, rest 🟩.
- Happy path: revealing the whole puzzle still triggers the finish screen and the share is all 🟨.
- Edge case: timer pauses on tab blur and resumes on focus.
- Edge case: finish detection on the *last keypress* triggers the finish screen exactly once, not on subsequent edits.
- Edge case: share text contains date and time but no letters or clue text.
- Integration: end-to-end solve in a JSDOM test produces a finish screen and a copyable share string.

**Verification:**
- `npm test` (web) passes
- Manual solve hits finish screen and produces a working share

---

- U12. **Frontend: streak tracking in localStorage**

**Goal:** Track the user's completion streak across sessions, with the rule "completion = streak day, off-days skip, no grace."

**Requirements:** R6, R8

**Dependencies:** U11

**Files:**
- Create: `web/lib/storage.ts` — `getStreak()`, `recordCompletion(date)`, etc.
- Create: `web/components/StreakBadge.tsx` — small persistent badge on the puzzle/home screen
- Modify: `web/components/FinishScreen.tsx` — show streak count, increment via `recordCompletion`
- Modify: `web/app/page.tsx` — render `<StreakBadge>` in the header
- Create: `web/tests/storage.test.ts`

**Approach:**
- `localStorage` schema (single key, JSON-serialized): `{ completedDates: string[]; lastSeen: string; settings: {...} }`. `completedDates` is a sorted array of ISO dates.
- Streak count = length of the longest *consecutive run* of `completedDates` ending at the most recent puzzle day, where consecutive *skips off-days*. To compute "off-days," we need to know which dates had puzzles. v0 simplification: a date with no `puzzles/<date>.json` is treated as an off-day (the frontend already handles this via the 404 path; we can either expose a small API for "did a puzzle exist on date X" or just check the file). Simplest: keep a separate list of "known off-days" the frontend has observed (when it 404s for a date); compute streaks by stepping back day-by-day, skipping known off-days.
- Backfill behavior: if the user opens the app days late and missed a *puzzle* day they didn't complete, the streak breaks. If they missed only off-days, streak stands.
- All streak logic runs client-side; no server.

**Patterns to follow:** Single localStorage key + JSON; debounced writes.

**Test scenarios:**
- Covers R6 and R8 directly.
- Happy path: completing today's puzzle increments the streak from 0 to 1.
- Happy path: completing puzzles on consecutive game days produces a streak equal to the run length.
- Edge case: an intervening off-day (no puzzle existed) does not break the streak.
- Edge case: missing a *puzzle* day (puzzle existed, user didn't complete) breaks the streak on next visit.
- Edge case: opening the app after a long absence with multiple missed days correctly reports streak = 0 if any of those days had puzzles the user didn't solve.
- Edge case: a tampered `localStorage` value (manually edited JSON) is detected and resets streak gracefully rather than crashing.
- Edge case: completing the same date twice (e.g., refresh) does not double-count.

**Verification:**
- `npm test` (web) passes
- Manual: solve today, check streak shows 1; clear localStorage, refresh, streak resets

---

- U13. **PWA polish + Vercel deploy**

**Goal:** The site is installable as a PWA and deployed publicly.

**Requirements:** R5, R7, R9

**Dependencies:** U10, U11, U12

**Files:**
- Create: `web/public/manifest.webmanifest`
- Create: `web/public/icons/` (192, 512 PNGs — placeholder until real branding)
- Create: `web/app/sw.ts` (or use `next-pwa` if it cleanly supports App Router; otherwise hand-roll)
- Modify: `web/app/layout.tsx` — link manifest, register service worker
- Create: `vercel.json` if needed for headers/caching

**Approach:**
- Manifest: name, short_name, icons, theme_color, background_color, display: "standalone", start_url: "/".
- Service worker: cache the app shell; for `/puzzles/*.json`, network-first with stale-while-revalidate so a freshly committed puzzle reaches users quickly.
- Vercel: connect the GitHub repo, set build dir to `web/`. No env vars needed for v0.
- Domain: free `*.vercel.app` for v0; custom domain is post-v0 polish.

**Patterns to follow:** Standard Next.js PWA recipe.

**Test scenarios:**
- Test expectation: limited to manual smoke on real devices —
  - "Add to Home Screen" works on iOS Safari and Android Chrome.
  - Offline: opening the app with no network shows the cached app shell + last-cached puzzle.
  - A new puzzle commit lands on the live site within a few minutes.

**Verification:**
- Lighthouse PWA score ≥ 90 on the deployed site
- `vercel.app` URL is live and serves today's puzzle

---

## System-Wide Impact

- **Interaction graph:** Pipeline (Python on GH Actions) and frontend (Next.js on Vercel) interact only through `puzzles/*.json` committed to `main`. No runtime API contract; no shared state. The schema (U2) is the entire contract surface.
- **Error propagation:** Pipeline failures are loud — they fail the GH Actions run and don't ship a puzzle. The frontend's *only* failure mode is "puzzle JSON missing or malformed" → frontend treats both like "no puzzle today" with a clear message. This keeps blast radius small.
- **State lifecycle risks:** All user state lives in `localStorage`. Risks: clearing browser data wipes streaks (acceptable v0 trade-off, documented). Risks: schema changes to the localStorage shape need a migration helper (out of scope for v0; document a plan for v0.5+).
- **API surface parity:** None — no public API in v0.
- **Integration coverage:** The U2 schema is exercised on both ends in unit tests (U2). U8's e2e test exercises the full pipeline. U11's JSDOM test exercises the full solve flow. We should also have *one* manual end-to-end check before the first real cron run: trigger the workflow on a recent past date, confirm the JSON is committed, confirm the live site renders it.
- **Unchanged invariants:** N/A — greenfield.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| nba.com endpoints rate-limit or break (`nba_api` is community-maintained against an unofficial API). | Cache responses to disk per date; have basketball-reference scraping as a documented fallback path; pipeline failure is loud, not silent — we'll know within a day. |
| Reddit's terms or rate limits change. | Single daily fetch with a clear User-Agent is well within polite bounds; OAuth fallback is a small future change if needed. |
| Anthropic API outage on a given morning. | Pipeline retries with backoff; on persistent failure, GH Actions run fails loud. We can manually trigger later in the day. v0 acceptable. |
| Grid fill algorithm fails to produce a valid grid for a given candidate set. | Algorithm gracefully drops candidates and retries; in the worst case, falls back to a "vanilla" wordlist fill with no NBA candidates required (still valid puzzle, just less themed). Document this fallback in U6. |
| Generated clue is bad / unfair / off-tone. | Accepted v0 risk — the whole point of v0.5 is the rate-and-rank loop. v0 ships imperfect; we learn from real shipped puzzles. |
| GH Actions cron drift across DST. | Cron is fixed UTC; the puzzle posts ~1 hour later in winter. Acceptable for v0; revisit if user feedback complains. |
| User clears browser data → loses streak. | Documented v0 trade-off; v1 introduces accounts. |
| Wordlist licensing. | Use a permissively-licensed source (e.g., scowl, broda); avoid copying any NYT data. Document the source in `pipeline/data/wordlist.txt` header. |

---

## Documentation / Operational Notes

- Update `README.md` with the architecture diagram + a "how the daily run works" section before the first public cron.
- Add a one-page `pipeline/README.md` covering local dev (`uv sync`, `python -m nba_mini.generate --date <past-date> --dry-run`).
- Add a one-page `web/README.md` covering local dev (`npm run dev`, env, Vercel deploy notes).
- Operational runbook: a small `OPERATIONS.md` (or `runbook.md`) at repo root listing: how to manually trigger the workflow for a missed day, how to roll back a bad puzzle (`git revert` the commit and trigger a fresh run with `--force`), how to update season context.
- After v0 ships, plan to write `context-engineering/solutions/best-practices/clue-prompt-iterations-2026-XX-XX.md` capturing prompt patterns that produced good clues.

---

## Sources & References

- **Origin document:** [context-engineering/brainstorms/2026-05-15-nyt-nba-crossword-design.md](../brainstorms/2026-05-15-nyt-nba-crossword-design.md)
- **Visual companion:** [context-engineering/brainstorms/mockups/index.html](../brainstorms/mockups/index.html)
- Project rules: [CLAUDE.md](../../CLAUDE.md)
- External (deferred to implementation): `swar/nba_api` GitHub, Anthropic Claude docs, Next.js PWA recipes
