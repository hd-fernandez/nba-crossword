# nba-crossword Project Status

**Last updated:** 2026-06-01

This doc is the single-page answer to "where are we and what's left." Update it after every major milestone or session pause. Treat it as the always-current map; brainstorms and plans are the deeper docs underneath.

---

## What's done

- **v0 — NBA daily crossword.** Pipeline (Python on GH Actions), Next.js PWA frontend, schema, tests, deploy-ready.
- **v2 — WNBA peer league.** `/nba` and `/wnba` with smart redirect at `/`. Per-league streaks, season contexts, palettes (NBA red / WNBA orange). Cross-league discovery chip.
- **v3 — Spelling Bee.** Hand-curated names corpus + active-roster auto-merge from `nba_api`. Six implementation units (corpus → schema → generator → hex UI → tier ladder → share). Three routes live: `/nba/bee`, `/wnba/bee`, `/all/bee`. GOAT celebration modal, share text, finish-dismiss state.
- **UX iteration round 1.** Photo backdrop, splash overlay with sequential `#N`, dismissable finish modal, auto-advance on word completion, real fonts (Fraunces + Inter).
- **Demo-readiness + reliability pass (2026-06-01).** Fixed the two demo-blocking bugs (stale dev shell needing hard-reload; wrong/stale date). Permanent WNBA generation with most-recent-slate per-league look-back; publish-vs-slate date split; index.json + walk-back fetch fallback; daily Bee generation CLI wired into cron; crisp grid lines; "Reveal one word" Bee hint. Then a full CE Review → Polish → Compound pass: cron per-league failure isolation, off-day streak self-correction, DST-aware publish date. Six learnings captured (see below).

Branch: `main` on `hd-fernandez/nba-crossword`. Latest commit: `91a1a0d`. Tests: 256 pipeline + 172 web passing. Routes: 7. Production build verified clean.

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

Two parts:

- **GH Actions cron** — workflow code is done: it assumes a Bedrock IAM role via GitHub OIDC (no static keys) and runs on the Bedrock backend with RSS ingest. **Blocked on a one-time AWS-side IAM setup** (register the OIDC provider, create the role + trust policy + Bedrock-invoke policy, set the `AWS_BEDROCK_ROLE_ARN` repo variable). Needs admin on account `042122908126` — likely the Data Strategy team. Full runbook: [reference/bedrock-oidc-setup.md](reference/bedrock-oidc-setup.md).
- **Vercel hookup** — code/config/build all done and verified: `npm run build` prerenders 7 static routes, zero runtime env vars, `vercel.json` pins framework + `npm run build` (load-bearing — fires the puzzle-sync prebuild hook) + `npm ci`. **Blocked only on the one dashboard step Vercel can't self-configure:** import the repo and set **Root Directory = `web`**. `vercel.json` can't set its own root (chicken-and-egg). Then walk the smoke checklist in `web/README.md`. Auto-deploys on every push to `main` after that.

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
- [Bedrock LLM backend](solutions/2026-05-29-bedrock-llm-backend.md)
- [Service-worker dev staleness](solutions/2026-06-01-service-worker-dev-staleness.md)
- [Publish vs slate date + per-league look-back](solutions/2026-06-01-publish-vs-slate-date.md)
- [index.json + walk-back fallback](solutions/2026-06-01-index-walk-back-fallback.md)
- [Per-league cache namespace](solutions/2026-06-01-per-league-cache-namespace.md)
- [Provisional state self-correction (streaks)](solutions/2026-06-01-provisional-state-self-correction.md)
- [Cron per-task isolation](solutions/2026-06-01-cron-per-task-isolation.md)

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
Both remaining blockers are external-account actions — all in-repo code/config is done.

- **Headless Bedrock auth (AWS IAM setup)** — blocks the cron. Workflow code is merged; someone with admin on AWS account `042122908126` must apply the IAM role + OIDC trust policy. Runbook: [reference/bedrock-oidc-setup.md](reference/bedrock-oidc-setup.md).
- **Vercel project creation** — blocks the live site. Needs Henry's Vercel login: import the repo, set Root Directory = `web`. Everything else is pinned in `vercel.json`.

---

## Open trivia for later

- Real WNBA hero photo (currently a generic basketball shot).
- Production icons (192/512/180 raster) — manifest shows a maskability warning until these land.
- Historical roster fold-in with fame-floor filter (NBA pre-active, WNBA pre-active).
