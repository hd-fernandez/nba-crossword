# Multi-League (WNBA) Expansion — Design Doc

**Date:** 2026-05-21
**Status:** Brainstorm — for v2 (after v0/v0.5 ship)
**Owner:** Henry Fernandez
**Origin context:** [2026-05-15 NYT NBA Crossword design](2026-05-15-nyt-nba-crossword-design.md)

---

## TL;DR

Same URL, same product identity, two leagues. The site shows "today's puzzle" and the *default league* depends on what's in season — NBA in season-ET-overlap months, WNBA when the NBA is dark. Users can always switch leagues manually. Per-league streaks. WNBA gets its own color treatment (orange-leaning) so the brand reads "basketball, but specifically *this* league today." Both leagues share the engine, the schema (with a `league` field), the pipeline shape, and the frontend code — they only differ in source feeds, season-context, and colorway.

**One-line pitch:** *If you read r/nba or r/wnba yesterday, you'll get today's puzzle.*

---

## Why this matters

Two reasons:

1. **The off-season problem.** The original brainstorm committed to "no games yesterday → no puzzle today." For a pure NBA app that means a puzzle ~25 days/month during the season and a long dormant stretch from late June (Finals end) through late September (preseason). WNBA's regular season runs roughly mid-May through late September with playoffs into October. **The two leagues' calendars complement each other almost perfectly.** A multi-league app has a daily puzzle ~340 days/year instead of ~200.
2. **The audience.** The same plugged-in fan who reads r/nba is increasingly likely to follow r/wnba — Caitlin Clark, A'ja Wilson, the Aces dynasty, the post-Sue Bird league restructuring. Treating WNBA as a first-class peer (not a fallback) is honest to the audience and the moment.

---

## Default-league selection (the trickiest UX decision)

The hard question: when a user opens the page on a date where *both* leagues had games yesterday, which puzzle do they see by default? Or where neither did? Or only one?

### The four cases

| Yesterday's slate | Default league for today |
|---|---|
| **NBA games + no WNBA games** | NBA (clean) |
| **WNBA games + no NBA games** | WNBA (clean) |
| **Neither league had games** | Most-recent league with a puzzle (sticky); on cold start, NBA |
| **Both leagues had games** | The user's "last played league" (sticky); on cold start, the *in-season* league per the calendar |

### Rules in plain language

- **Sticky preference.** Once a user has played a league, that's their default until they manually switch. We persist `lastPlayedLeague` in localStorage. This honors the "if you played WNBA yesterday, give me WNBA today" intuition without requiring accounts.
- **In-season override on cold start only.** A new visitor with no preference gets routed by the calendar — NBA from October–June, WNBA from May–October. The overlap month gets NBA on cold start (because the audience is bigger there at v2 launch).
- **Always show both.** Even when defaulted, the header has a clear toggle (`NBA · WNBA`) so the user can switch in one click. Switching becomes the new sticky.
- **Both-league days are surfaced, not hidden.** The header shows a tiny "Also today: WNBA" link when both leagues have a fresh puzzle. This is the engagement multiplier — a fan loyal to one league discovers the other passively.

### What "last played" means

A user "played" a league on date X if they completed (or revealed) that league's puzzle for date X. Just opening doesn't count. This rule keeps the sticky honest — if I bounce off the WNBA puzzle without solving, I'm not signaling preference.

---

## URL and routing

A few options were considered; chose **path-prefix per league with a smart root**.

### URL shape

```
/                  → 302 to /nba/ or /wnba/ based on default-selection rules above
/nba/              → today's NBA puzzle
/wnba/             → today's WNBA puzzle
/nba/2026-05-21    → archive (post-v2 — out of scope here, but URL leaves room)
/bee/              → spelling bee, league-agnostic landing (see bee brainstorm)
/nba/bee/          → NBA spelling bee
/wnba/bee/         → WNBA spelling bee
```

### Why path-prefix and not a query param

- Cleaner share links. `nbamini.app/wnba` reads as "the WNBA mini" — `?league=wnba` reads as a parameter.
- Cleaner cache rules at the CDN. Each path has its own cache key.
- Easier static rendering — Next's App Router maps cleanly to `app/(league)/page.tsx`.
- Future SEO: search engines treat them as separate pages, not query-string variants of one page.

### Why not separate subdomains (`nba.nbamini.app` / `wnba.nbamini.app`)

Costs more (more cert handling, more deploy targets), separates the brand more than the product wants. The whole point of the design is *one* daily ritual that happens to span two leagues.

---

## Visual identity per league

### NBA (current)

- **Hero color:** NBA red `#c8102e` (Start button, accents)
- **Background photo:** general basketball action (court.jpg, current)
- **Type:** Iowan/serif title, system body
- **Streak:** 🔥 N

### WNBA

- **Hero color:** WNBA orange — somewhere between `#e87722` (current WNBA branding) and a slightly cooler `#ff6b1a`. Test under the dark gradient to pick.
- **Background photo:** WNBA-specific action shot from Unsplash CC0 (or similar curated source). The same darkening treatment, just a different image.
- **Type:** Same Iowan/serif. Identity comes from color + image, not type.
- **Streak:** Still 🔥 N — but the streak count is *per-league*. A user with a 12-day NBA streak and 3-day WNBA streak sees both surfaced when they switch leagues. Don't merge the count; that destroys the meaning.

### Cross-league elements

- **Title format:** "The NBA Mini" / "The WNBA Mini" (same shape, league name swapped).
- **Puzzle numbering:** Independent per league. NBA Mini #042 and WNBA Mini #042 can coexist; the user reads them as separate counts.
- **Share text:** league baked into the tagline (`nbamini.app/wnba · May 21 · 1:24`).
- **Footer:** unchanged.

The constraint here is that everything that signals "league" is *visual* (color, image, header text, URL, share tagline). The grid mechanic, the timer, the reveals, the share grid — everything else is identical. This keeps engineering surface area small.

---

## Content scope per league

### What's the same

- Anything-goes answers (players, teams, slang, news, celebrities sighted courtside, "POSTER", "FLOPPER")
- 50/30/20 wry/discoursey/factual voice mix
- Mosaic editorial (no forced theme)
- Yesterday's discourse + box scores as inputs
- 5×5 grid

### What's different

- **Sources.** WNBA pulls from r/wnba (instead of r/nba), wnba.com box scores (instead of nba.com). Both leagues have similar Reddit + stats coverage; the API shapes are essentially the same.
- **Season context.** WNBA needs its own `season_context.md` snippet — different storylines, different phase of season, different recent drama. Currently for May 2026: WNBA regular season just opened, it's the post-Caitlin-Clark-rookie-year era, expansion teams (Golden State Valkyries) recently played their first games.
- **Wordlist NBA-skew.** The current wordlist is hand-tuned for NBA flavor. WNBA can either (a) use the same wordlist (most words are league-neutral) or (b) get a small WNBA-specific overlay. For v2 ship: same wordlist + a small overlay file with WNBA-specific names/terms. Iterate from there.
- **Clue prompts.** Same three voice files, but prompted with the relevant league's context. May need league-specific in-prompt examples in the few-shots — a wry-NYT example about LeBron doesn't transfer perfectly to a wry-NYT example about A'ja Wilson. Easy to swap in.

### What about overlap days?

Days when both leagues had games yesterday → both puzzles get generated. They're independent. Don't try to be clever (e.g., "today's puzzle is themed around an NBA-WNBA crossover"). The mosaic stays per-league. Simpler, more honest.

---

## Schema impact

The puzzle JSON gets a new required field:

```json
{
  "date": "2026-05-21",
  "league": "nba",            // ← new: "nba" | "wnba"
  "puzzle_number": 7,          // independent count per league
  "grid": { ... },
  "entries": [ ... ],
  "season_context_version": "...",
  "generated_at": "2026-05-21T10:00:00Z",
  "model": "claude-sonnet-4-5"
}
```

`puzzle_number` is independent per league. The old (v0/v1) puzzles in `puzzles/*.json` need a one-time migration to add `league: "nba"` — straightforward, scriptable.

### Storage layout

```
puzzles/
├── nba/
│   ├── 2026-05-21.json
│   ├── 2026-05-22.json
│   └── ...
└── wnba/
    ├── 2026-05-21.json
    ├── 2026-05-22.json
    └── ...
```

Frontend fetches `/puzzles/<league>/<date>.json`. The 404 path still triggers the dormant state — but now it's per-league, so a WNBA dormant day doesn't hide an NBA puzzle.

---

## Pipeline impact

### Generation runs once per league per day

The cron becomes two parallel jobs in the same workflow file (or two workflow files — TBD at plan time):

```yaml
jobs:
  generate-nba:
    runs-on: ubuntu-latest
    steps: [ ... fetch_yesterday_games(NBA) → generate → write puzzles/nba/<date>.json ... ]
  generate-wnba:
    runs-on: ubuntu-latest
    steps: [ ... fetch_yesterday_games(WNBA) → generate → write puzzles/wnba/<date>.json ... ]
```

Both jobs handle their own no-games-day exit (R6 still applies, per-league). On a both-leagues-had-games day, both jobs commit a file; on a neither-leagues day, no commit, no puzzle.

### Pipeline code changes

Most of the pipeline is league-agnostic by design. The hot spots:

- `nba_mini.ingest.reddit` — needs a `subreddit` parameter (default `nba`, also `wnba`).
- `nba_mini.ingest.nba_stats` — already wraps `nba_api`. The `nba_api` package supports both leagues; the call shape barely changes (different endpoints for WNBA box scores). Worth confirming at plan time.
- `nba_mini.season_context` — needs to load from one of two markdown files based on which league we're generating for. `season_context_nba.md` and `season_context_wnba.md`.
- `nba_mini.generate` — takes a `--league nba|wnba` flag. The orchestrator threads league through to ingestion + season-context + output path.
- `nba_mini.clues` — voice prompts probably stay the same; the `GenerationContext` carries the season-context text already, which is league-aware.

The schema change (`league` field) is a one-line addition.

### Pipeline cost

Roughly 2x today's Anthropic spend on overlap days, ~1x on single-league days. Total monthly: still well under $20, probably under $10 once we have efficient prompts. If Snowflake Cortex is the LLM provider (current direction), this is just more credit burn, not a separate bill.

---

## Frontend impact

### Routing changes

Restructure `app/`:

```
app/
├── page.tsx                     → smart redirect to default league
├── (league)/
│   ├── nba/
│   │   ├── page.tsx
│   │   └── bee/page.tsx
│   └── wnba/
│       ├── page.tsx
│       └── bee/page.tsx
```

The smart-redirect at root is a tiny client component that reads `lastPlayedLeague` from localStorage, falls back to calendar logic, then `router.replace('/<league>')`. SSR delivers a redirect-shell with a loading state.

### State changes

- `lastPlayedLeague` lives in `localStorage`, separate from streaks but in the same single-key blob.
- `completedDates` and `knownOffDays` become per-league: `{ nba: { completedDates, knownOffDays }, wnba: {...} }`. One-time migration on v2 launch reads the old flat fields and assigns them to NBA.
- `<StreakBadge>` becomes league-aware: takes a `league` prop, shows the streak for that league specifically.
- League-switch toggle in the header. One click, no confirmation, cheap fetch of the other league's puzzle.

### Cross-league discovery

When the user is on the NBA puzzle and the WNBA puzzle for today *also* exists, show a small chip in the header: `Also today → WNBA Mini #N`. Clickable. This is the multiplier — passive cross-league exposure that doesn't disrupt the user's chosen flow.

---

## Edge cases worth thinking about

- **A user with a long NBA streak who tries WNBA for the first time.** Their NBA streak is preserved, untouched. They start fresh on WNBA at streak 0. The badge shows the active league's streak.
- **WNBA Finals end mid-October; NBA preseason starts late September.** ~2-week overlap. Both puzzles run. Default for new users tilts NBA (bigger audience). Existing users get whatever they last played.
- **All-Star breaks (NBA Feb, WNBA July).** Both leagues have ~5-day mid-season breaks. No-games-day rules apply per league. Streaks skip per league.
- **WNBA off-season is much shorter.** Mid-October to mid-May is dormant for WNBA. NBA fills almost all of it. The two-league app is "always live" in practice.
- **A solver in Europe at 4am their time.** US/Eastern day boundary still applies. We're not solving for global users in v2 — that's a v3 conversation.
- **Both leagues have a Game 7 the same night.** Glorious. Both puzzles ship; the discovery chip works overtime. No special handling needed.

---

## Roadmap placement

**v2 — multi-league.** The right time is *after* v0/v0.5 prove the engine. Specifically:
- v0 ships with `league: "nba"` baked into every puzzle (tiny change to lock the schema)
- v0.5 layers in candidate ranking + rate-and-rank for clue quality
- **v2 is multi-league.** WNBA gets its own ingest, season context, prompts, and cron job. Frontend gets the league prefix and toggle.

Why not v1? Because v1 was already earmarked for native iOS + push + accounts in the original brainstorm. Keep that. Multi-league is its own discrete piece of work and deserves its own version slot.

If v2 is too far out, we can do a **"locked WNBA placeholder"** in v1 — the schema + URL accept league: wnba, but we manually maintain a hand-curated WNBA puzzle weekly, no automation. Tests the audience appetite without building the full pipeline. Decide at v1 plan time.

---

## Open questions parked for the implementation plan

- ~~**Domain.** Is `nbamini.app` the brand, or do we go with something league-neutral like `dailyhoops.app`?~~ **Decided 2026-05-21:** `nbamini.app` stays. Slight "but it says NBA in the URL" weirdness on WNBA pages, but acceptable trade-off; brand recognition > naming purity at this scale.
- **Wordlist split or shared.** Empirical question — try shared first, see what falls out, build an overlay only if needed.
- **Reddit auth.** WNBA subreddits have lower volume; rate limits aren't an issue, but the same OAuth question applies as for NBA. Almost certainly fine on the public JSON endpoints.
- **wnba.com vs nba_api package.** `nba_api` claims WNBA support — confirm at plan time it's actually maintained.
- **Default-language pivots based on time of day?** When the West Coast WNBA late game is still in progress at midnight ET, "yesterday's games" might miss it. Probably handled by the same generation timing the NBA cron uses (06:00 ET) — by then everything is final. Confirm at plan time.
- **Photo licensing for WNBA action shots on Unsplash.** Verify there's a deep-enough catalog of CC0 WNBA imagery; if not, we may need a single hero photo and a rotation strategy.
- **The "Also today" cross-league chip.** Is it a v2 ship or v2.5 polish? Probably ship — it's the highest-leverage piece of the multi-league UX.

---

## Sources & References

- Origin v0 brainstorm: [2026-05-15-nyt-nba-crossword-design.md](2026-05-15-nyt-nba-crossword-design.md)
- Sibling brainstorm shipped same day: [2026-05-21-spelling-bee-design.md](2026-05-21-spelling-bee-design.md)
- WNBA branding reference: official WNBA color palette (orange `#e87722`)
- `nba_api` package: confirm WNBA endpoint coverage at plan time
