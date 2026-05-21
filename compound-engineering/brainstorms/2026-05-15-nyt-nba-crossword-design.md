# NYT-style NBA Mini Crossword — Design Doc

**Date:** 2026-05-15
**Status:** Brainstorm complete, ready to plan
**Owner:** Henry Fernandez
**Repo:** [hd-fernandez/nba-crossword](https://github.com/hd-fernandez/nba-crossword)

---

## TL;DR

A daily 5×5 mini crossword whose clues refresh from yesterday's NBA discourse — last night's games, r/nba conversation, news, trades, drama. Voice is mostly wry-NYT with real online-discourse flavor and a factual floor. Pipeline is fully automated; quality compounds via a "rate the candidates" loop. Ships as a PWA. v0 has no accounts and no push.

**One-line pitch:** *If you read r/nba yesterday, you'll get this puzzle.*

---

## Audience

**Plugged-in current NBA fans, not historians.** Solvers who follow the league closely day-to-day — rotations, beat writers, current memes, this week's storylines. Not casuals (won't get half the clues), not historians (don't need 1986 Finals trivia).

Implication: clues can assume current context without exposition. "Dropped 40 on BOS last night" works without naming the player. The puzzle rewards being tapped in.

---

## Content scope

**Anything goes — answers and clues both.** No restriction to players, teams, or basketball vocabulary. Answer can be `CHALAMET` (front-row sighting), `FLOPPER` (last night's discourse), `POSTER` (the dunk that broke the internet), `EJECTED`, or any English word — provided the *clue* anchors it in yesterday's NBA universe.

The puzzle is a **cultural snapshot of yesterday's NBA**, not a stat quiz.

### Clue voice mix (target distribution)

| Voice | Share | Example |
|---|---|---|
| Wry NYT-style | 50% | "Visited TD Garden, scored 40, left." |
| Online/discoursey | 30% | "BOS got cooked by him for 40." |
| Factual | 20% | "Dropped 40 on BOS last night." |

This is a v0 target, tuned over time via the rate-and-rank loop.

### Editorial structure

**Mosaic, not themed.** Each puzzle is a sampler of yesterday's biggest moments — entry from Game A, entry from a trade, entry from a viral clip, entry from a presser quote. No forced single theme. Themes emerge naturally on huge nights (Game 7s, deadline day, draft night) but the pipeline does not try to engineer them.

### Calendar rule

- Games yesterday → puzzle today
- No games yesterday → no puzzle today
- App goes dormant on All-Star break, dead summer days, the day after the Finals end
- Streaks **skip** off-days, don't break

---

## Data sources

**v0 ingest = r/nba + nba.com box scores.** No X/Twitter (cost, rate limits). No beat-writer scraping. No highlight feeds.

| Source | Role | Notes |
|---|---|---|
| r/nba | Primary discourse signal | Top posts, game threads, post-game threads, comment-level extraction. Free via Reddit JSON API. |
| nba.com box scores | Grounding layer | Who played, who scored, who was ejected. Use `nba_api` Python package or basketball-reference as fallback if nba.com is hostile to scraping. |

**v1 candidates** (deferred): X/Twitter via paid scraping, beat writers via RSS, House of Highlights.

### Two layers of context

The pipeline ingests on two cadences because the same event reads differently depending on calendar position:

1. **Daily input** (runs every morning) — yesterday's games, r/nba top posts/comments, news from the past 24 hours
2. **Season context** (refreshes weekly or on major events) — what phase of the calendar are we in, which storylines are live. Currently: *2026 Conference Semis · Wemby's first ejection last week · post-Draft-Lottery · post-All-Star.*

Season context is small (a paragraph or so), high-leverage. It gets prepended to every clue-writing prompt so a 40-point game in May reads as a *playoff* 40-point game, not a regular-season one.

---

## Generation pipeline (conceptual)

```
yesterday's r/nba (top posts, top comments, game threads)
        +
yesterday's box scores (nba.com / nba_api)
        +
season context (weekly snapshot)
        ↓
   [extract themes, players, moments, words, slang]
        ↓
   [pick ~5-7 candidate answers across the day's surface]
        ↓
   [fill 5x5 grid around them]
        ↓
   [for each entry: generate clues in 3 voices, pick by target distribution]
        ↓
   [generate N candidate puzzles for the night]
        ↓
   [LLM-as-judge ranks candidates against eval criteria]
        ↓
   [highest-ranked candidate ships as today's puzzle]
        ↓
   [Henry rates candidates A/B/C with one-line reason → fed back as few-shots]
```

**Generation = Claude Sonnet. Judge = Claude Opus.** Cheap-to-good ratio is right.

### The "compounding" loop

Pure automation doesn't reach NYT-quality, but it *can* compound if edits and ratings are captured:

- Pipeline ships **multiple candidate puzzles** for each night
- Henry rates them (A/B/C + one-line reason — *why* B was better than A)
- Ratings logged to a small dataset
- Top-rated examples become **few-shot examples** in the generation prompt
- Over weeks, the model learns the house voice from your taste

This loop is **first-class infrastructure**, not a nice-to-have. Without the rating capture, automation flatlines at "good enough."

---

## Solver UX

### Grid

- **5×5 fixed** for v0. No bigger Sundays, no adaptive sizing. The ritual is the product.

### Solve experience

- **Timer visible by default**, toggleable to hide
- **NYT-style reveals** allowed (letter / word / puzzle) but **tracked** — revealed cells render differently in the share grid (e.g., asterisk or different color), so the share stays honest without invalidating the solve
- **Finish screen:** confetti, time, streak count, share button — NYT/Wordle-style

### Share mechanic

- Wordle-style emoji grid + clean tagline (`nbamini.app · May 14`)
- **Spoiler-free** — no answer reveals, no theme references
- Revealed cells get a different emoji (e.g. 🟨 vs 🟩) so a clean solve is distinguishable from a reveal-heavy one
- No NBA-flavored emoji in the share itself (rendering inconsistency across platforms); save that for the in-app celebration

### Streaks

- **Completion = streak day**
- Off-days **skip** (don't count, don't break)
- **No grace mechanic** for v0
- Streak visible on finish screen + small persistent badge on the puzzle/home screen
- Stored in `localStorage` (no accounts in v0 — see Stack)

---

## Stack & infra

Side-project scale. ~$0–10/month target.

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js (React) on Vercel | Solid PWA support, easy deploy, ecosystem covers everything we'll need (stats, auth in v1) |
| Puzzle storage | Static daily JSON committed to repo | `puzzles/YYYY-MM-DD.json` — frontend just fetches |
| User state | `localStorage` (no accounts) | Streaks, completion, timer history live in the browser. Loses on device switch; acceptable for v0. |
| Generation pipeline | GitHub Actions, daily cron at ~6am ET | Free, dead simple, commits the new puzzle JSON to the repo. Public logs if public repo. |
| LLM (generator) | Claude Sonnet via Anthropic API | Cost-efficient for the volume |
| LLM (judge / rate-rank) | Claude Opus | Reserved for the per-night candidate ranking step |

### Deferred to v1+

- Native iOS app
- Push notifications (8am ritual)
- User accounts + cloud-synced streaks
- Leaderboards / friend graphs
- X/Twitter as a discourse source

---

## Roadmap

### v0 — "ship the engine" (target: weeks, not months)
- Build the daily ingest (r/nba + nba.com)
- Build season-context snippet (manually maintained at first)
- Build generator pipeline producing 1 puzzle/day
- Build PWA frontend with grid, timer, reveals, finish screen, share
- Streaks via localStorage
- Daily JSON committed by GitHub Actions
- **No human approval in the loop** — pipeline ships unattended

### v0.5 — "compound the quality"
- Pipeline produces **N candidate puzzles** per night, not 1
- LLM-as-judge ranks them, top one ships
- Henry rates candidates retrospectively (A/B/C + reason)
- Rating log feeds few-shot examples into the generation prompt
- Eval set built from highly-rated candidates

### v1 — "earn the ritual"
- Native iOS app (or stay PWA + add proper web push)
- 8am push notifications
- User accounts + cloud-synced streaks
- Friend leaderboards / share-time competitions
- Add X/Twitter as a discourse source if missing material is a real problem

### v2 — "two leagues, one ritual"
**See:** [2026-05-21-multi-league-wnba-design.md](2026-05-21-multi-league-wnba-design.md) for the full design.

- WNBA puzzle as a first-class peer to NBA, not a fallback
- Path-prefixed routing: `/nba/` and `/wnba/` with smart-default at `/`
- Per-league streaks, season contexts, and visual identities (orange-leaning WNBA palette)
- Cron generates both leagues per day; either, both, or neither may have puzzles
- Sticky last-played-league preference; calendar fallback for cold starts
- "Also today: WNBA" cross-league discovery chip
- Schema gets a required `league` field; existing puzzles back-migrated to `league: nba`

### v3 — "Hoops Spelling Bee"
**See:** [2026-05-21-spelling-bee-design.md](2026-05-21-spelling-bee-design.md) for the full design.

- NYT-Bee mechanic with hoops player/coach/owner last names as the corpus
- Hoops-flavored tier ladder: Undrafted → G League call-up → Rookie → Sophomore → Vet → All-Star → Champion → Hall of Famer → GOAT
- Three flavors: `/nba/bee`, `/wnba/bee`, `/bee` (combined)
- Pre-computed daily puzzles from a curated names corpus; refreshed quarterly
- Operating cost ~$0 (no LLM in the Bee loop)
- Cross-promotional surfaces between crossword and Bee on the same league

### Later / maybe
- Sunday extended puzzle
- Themed puzzles for marquee events (Game 7, deadline, draft, opener)
- Archive / play-old-puzzles mode (probably needs accounts)
- Subscription tier (NYT model)
- G League / EuroLeague / NCAA expansions (way later — only if the two-league rhythm proves itself)

---

## Open questions parked for the implementation plan

- Exact 5×5 grid construction algorithm — write our own, port an existing one, or LLM-driven? Affects fillability rate vs. quality.
- nba.com vs basketball-reference vs `nba_api` package — which is most reliable for v0? (Probably try `nba_api` first.)
- r/nba scraping — Reddit's JSON API has been stable, but worth confirming auth requirements as of 2026.
- Season-context maintenance — fully manual at first, or LLM-summarized weekly with a manual review? v0 = manual, document a path to automated.
- Eval criteria for the LLM-as-judge — what does "good clue" actually mean in measurable terms? Needs a working definition before v0.5.
- Reveal accounting in the share grid — exact emoji mapping (🟩 clean / 🟨 revealed letter / 🟧 revealed word?) needs UX pass.
- Streak edge cases — what happens if a user opens the app days late? Auto-skip the missed days as if they were off-days, or count as a break? (v0 default: backfill missed off-days, but a missed *puzzle* day breaks streak.)

---

## Visual companion

Live mockups at [compound-engineering/brainstorms/mockups/index.html](mockups/index.html) — placeholder grid + share card + streak strip. Will iterate alongside the implementation plan.

---

## Next step

Hand off to **`/ce-plan`** to produce a v0 implementation plan with specific milestones, file structure, and first-week tasks. Plan should reference this doc as the source of truth and not relitigate decisions made above.

---

## Status update — 2026-05-21

**v0 is implemented and on `feat/v0-foundation`.** Round-1 UX iteration shipped: photo background, splash overlay with sequential puzzle numbering, dismissable finish screen, auto-advance on word completion. Pending real-clue demo (waiting on Snowflake Cortex auth — no Anthropic API key available).

**Roadmap collapsed.** v0.5 quality work and v1 native-app work both deferred indefinitely. Going straight from v0 to **v2 (multi-league WNBA)** because scope-expansion identity ("we are a basketball app, not an NBA app") is the right thing to commit to before more polish on a single-league product. Quality work folds in as we iterate.

Two new directions added to the roadmap (v2 multi-league, v3 Spelling Bee) — see brainstorm sibling docs linked from the Roadmap section above.
