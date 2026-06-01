# nba-crossword Project Status

**Last updated:** 2026-05-29

This doc is the single-page answer to "where are we and what's left." Update it after every major milestone or session pause. Treat it as the always-current map; brainstorms and plans are the deeper docs underneath.

---

## What's done

- **v0 — NBA daily crossword.** Pipeline (Python on GH Actions), Next.js PWA frontend, schema, tests, deploy-ready.
- **v2 — WNBA peer league.** `/nba` and `/wnba` with smart redirect at `/`. Per-league streaks, season contexts, palettes (NBA red / WNBA orange). Cross-league discovery chip.
- **v3 — Spelling Bee.** Hand-curated names corpus + active-roster auto-merge from `nba_api`. Six implementation units (corpus → schema → generator → hex UI → tier ladder → share). Three routes live: `/nba/bee`, `/wnba/bee`, `/all/bee`. GOAT celebration modal, share text, finish-dismiss state.
- **UX iteration round 1.** Photo backdrop, splash overlay with sequential `#N`, dismissable finish modal, auto-advance on word completion, real fonts (Fraunces + Inter).

Branch: `main` on `hd-fernandez/nba-crossword`. Latest commit: `cdba564`. Tests: 219 pipeline + 151 web passing. Routes: 7.

---

## What's left, in order

### 1. LLM auth — RESOLVED via Bedrock (2026-05-29)

The Snowflake-Cortex path is abandoned. Claude is reachable through **Amazon Bedrock** using Henry's existing AWS SSO profile (`nba-bedrock`, account `042122908126`, role `Data-Strategy-Team-Access`, region `us-east-1`) — the same path Claude Code itself uses (`CLAUDE_CODE_USE_BEDROCK`). No API key, no admin request needed.

Wired into the pipeline as a selectable backend:
- `BedrockClueLLM` in `pipeline/nba_mini/clues.py` (sibling of `AnthropicClueLLM`, shares `_extract_text`).
- `Deps.production(backend=...)` selects `"anthropic"` or `"bedrock"`; defaults to `$NBA_MINI_LLM_BACKEND` then `"anthropic"`.
- CLI: `python -m nba_mini.generate --backend bedrock`.
- **Gotcha:** Bedrock requires the region-prefixed *inference-profile* ID (`us.anthropic.claude-sonnet-4-6`), not the bare model ID — `BEDROCK_DEFAULT_MODEL`.

Verified live: today's NBA + WNBA puzzles (2026-05-29) have real Bedrock-generated clues.

### 2. Refine clues + answer picks

Now unblocked. Generate 3–5 real puzzles, Henry rates them, prompt files in `pipeline/nba_mini/prompts/` get edited, regenerate. The rate-and-rank loop — the work that makes the product *good*.

### 3. Reddit ingest — RESOLVED via RSS (2026-06-01)

The `.json` endpoint 403s (Reddit hard-blocks anonymous JSON; UA tweaks don't help). Fixed by switching the live default to the public Atom feed at `/r/<sub>/top/.rss`, which still serves 200 with no auth.
- `fetch_yesterday_discourse_rss` in `pipeline/nba_mini/ingest/reddit.py` is the production path; `Deps.production` uses it.
- Trade-off: RSS gives titles + flair + timestamps + permalinks but **no comment bodies or scores** (`top_comments=[]`, `score=0`). Titles carry the discourse signal the clue prompt needs.
- The old JSON path is kept intact (fixture-tested) for a future OAuth-app upgrade if comments are wanted back.
- **Verified:** full pipeline now runs end-to-end with real RSS discourse + real Bedrock clues, no stubs.

### 4. Production deploy

Vercel hookup + GH Actions cron on a schedule. The cron still needs a Bedrock auth path that works headless (IAM role via OIDC — the runner has no SSO session). The Reddit half of the old cron failure is now fixed.

### 5. (Optional) U7 — Bee generator algorithm tuning

WNBA Bees still cap at ~3–4 valid names per puzzle even after expanding the corpus to ~150 names. Diagnosed as algorithm bottleneck, not data depth: the greedy first-match board-pick walks away from richer boards. Broader board search + scoring would lift NBA from ~10 to 15+ and WNBA into the same range. See [solutions/2026-05-26-bee-v3.md](solutions/2026-05-26-bee-v3.md).

---

## Brainstorms + plans

- [v0 NBA crossword design](brainstorms/2026-05-15-nyt-nba-crossword-design.md)
- [v2 multi-league WNBA](brainstorms/2026-05-21-multi-league-wnba-design.md)
- [v3 Spelling Bee](brainstorms/2026-05-21-spelling-bee-design.md)
- [v0 plan](plans/2026-05-17-001-feat-nba-mini-v0-plan.md)
- [v2 skeleton plan](plans/2026-05-21-002-feat-multi-league-wnba-skeleton-plan.md)
- [v3 skeleton plan](plans/2026-05-21-003-feat-spelling-bee-skeleton-plan.md)
- [v3 learnings](solutions/2026-05-26-bee-v3.md)

---

## Locked decisions

- **Domain:** `nbamini.app` stays. Brand recognition wins.
- **Default-league rules:** sticky last-played > calendar-driven (Oct–Apr NBA, May–Sep WNBA). NBA wins overlap-month tiebreak on cold start.
- **Per-league streaks** (independent, no merging).
- **Bee corpus:** last names + mononym first names + iconic nicknames. Fame floor: NBA 100 games OR award OR currently active; WNBA 3 seasons OR award OR currently active.
- **Bee tiers:** Undrafted → G League call-up → Rookie → Sophomore → Vet → All-Star → Champion → Hall of Famer → GOAT.
- **Roadmap collapsed:** v0.5 quality work and v1 native-app work both deferred indefinitely. v0 → v2 → v3 shipped.

---

## Blockers

- **~~Snowflake auth~~ — RESOLVED.** Abandoned Snowflake-Cortex; using Amazon Bedrock via AWS SSO instead (see What's-left #1). No outstanding LLM-auth blocker for local runs.
- **~~Reddit 403~~ — RESOLVED.** Switched to the public RSS feed (see What's-left #3).
- **Headless Bedrock auth** — the only thing standing between us and a working cron. The GH runner has no SSO session; needs an IAM role assumed via OIDC (or creds in secrets). See What's-left #4.

---

## Open trivia for later

- Real WNBA hero photo (currently a generic basketball shot).
- Production icons (192/512/180 raster).
- Vercel project setup (root dir = `web/`).
- Historical roster fold-in with fame-floor filter (NBA pre-active, WNBA pre-active).
