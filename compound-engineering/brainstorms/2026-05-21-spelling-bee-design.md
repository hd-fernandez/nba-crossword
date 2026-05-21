# Hoops Spelling Bee — Design Doc

**Date:** 2026-05-21
**Status:** Brainstorm — for v2/v3 (after multi-league lands)
**Owner:** Henry Fernandez
**Origin context:** [2026-05-15 NYT NBA Crossword design](2026-05-15-nyt-nba-crossword-design.md), [2026-05-21 multi-league WNBA design](2026-05-21-multi-league-wnba-design.md)

---

## TL;DR

NYT Spelling Bee mechanic, but words must be valid NBA / WNBA player, coach, or owner *last names*. Seven letters total: one center letter (must be used in every name), six surrounding letters. Names must be ≥ 4 letters, must use the center letter, can reuse letters. The score-tier system is hoops-themed: Rookie → Sophomore → Vet → All-Star → Champion → Hall of Famer → GOAT. Lives at `/bee` (league-agnostic), `/nba/bee`, `/wnba/bee`. Same daily-ritual cadence as the crossword, runs in parallel.

**One-line pitch:** *Spelling Bee, but every word is a name a tapped-in fan would recognize.*

---

## Why this game

The Spelling Bee mechanic is *very* good — it's NYT's most-played game after the crossword, and the daily-ritual + tier-progression dynamic is an even tighter engagement loop than crossword-style "you either solved it or you didn't." A hoops-themed Bee gives the audience:

- A second daily ritual on the same site (drives DAU per visit).
- A "lower stakes" daily — a Bee session is dippable; you can play 60 seconds and feel progress; you can come back at lunch and add three more words.
- A *different* skill test from the crossword. The crossword rewards reading discourse; the Bee rewards knowing the names. Different aspects of fandom; some users will be better at one than the other.

The brainstorm question isn't "should we build this" — it's "how do we make a hoops Bee feel as native to its source material as our crossword does."

---

## Core mechanic (kept faithful to NYT Bee)

- **Seven letters in a hexagonal layout.** One center letter (highlighted, e.g., red on cream), six surrounding letters (neutral). Same visual language NYT uses.
- **Form names by tapping letters or typing.** A name appears in the entry bar; submit by Enter / tap the submit button.
- **Validity rules:**
  - Minimum 4 letters
  - Must use the center letter
  - Can reuse letters as many times as needed
  - Must be a valid name in our **names corpus** (see below)
- **Pangram bonus:** Names that use *all 7 letters* score extra. NYT bonus is +7 points; we keep it.
- **Score:** 4-letter name = 1 point. Each additional letter = +1. Pangram = letter count + 7. Same as NYT.
- **Shuffle button.** Reorders the 6 outer letters. Center stays put.
- **Found-names list.** Sorted alphabetically as the user adds them. Hidden by default behind a "Show found names" toggle so progress isn't telegraphed.

What's *different* from NYT Bee:

- **Names, not common words.** The acceptance dictionary is people, not vocabulary.
- **Hoops tier names** instead of NYT's tier ladder.
- **Per-league corpus.** NBA bee accepts NBA names only; WNBA bee accepts WNBA names only. The league-agnostic `/bee` accepts both — see "Three flavors" below.

---

## The names corpus

This is the load-bearing decision. The corpus determines what's accepted, and the corpus determines what daily puzzles can be generated.

### What counts as a name

- **Player last names** (current rosters + all-time, per league)
- **Mononym-grade first names** — LeBron, Giannis, Kobe, Magic, Shaq, Kareem, Wemby, A'ja, Caitlin, Sue, Sabrina, Diana. Test: would a fan recognize this in *SportsCenter* shorthand? If yes, it's in.
- **Distinctive nicknames** that have crossed into mainstream coverage — Greek Freak, King James, Black Mamba. *Not* fan-invented Twitter shorthand.
- **Coach last names** (current head + assistants worth knowing)
- **Owner / front-office last names** (worth knowing — Cuban, Lacob, Tepper, etc. for NBA; Mark Davis, Joe Tsai for various)
- **Iconic figures** that any tapped-in fan would recognize even if they don't currently fit a roster slot (Jordan, Kobe, Stockton, Lobo, Swoopes, Bird-Sue, etc.)

Excluded:

- **Common first names that aren't iconic** (Mike, John, Chris) — too generic; "Mike" could be anyone.
- **Made-up Twitter nicknames** that haven't crossed into mainstream coverage.
- Team names (different game)
- City names (different game)

### Corpus storage shape

Each name in the corpus is stored as `name | type | display`:

| Field | Example | Notes |
|---|---|---|
| `name` | `LEBRON` | Uppercase, diacritics-stripped, used for matching |
| `type` | `first_mononym` | One of: `last`, `first_mononym`, `nickname` |
| `display` | `LeBron James` | Original casing + punctuation, for the found-names list |

This lets `LEBRON` and `JAMES` both be valid Bee answers on the same board (different `type`, different `display` — same player). The Bee scorecard lists them separately.

### Source

- **Players (active):** the `nba_api` package's player rosters, both leagues. We already use it for box scores; it carries the full active-player list.
- **Players (historical):** basketball-reference scrape or the `nba_api` historical endpoints. Probably one-time scrape into a static `data/names_<league>.txt`, refreshed quarterly.
- **Coaches:** smaller list, hand-curated initially, then automated against a beat-writer reference at v3.
- **Owners / FO:** small list, hand-curated, rarely changes. ~30 names per league.

### Length and shape

- Last names of length 4–10. Names ≥ 11 letters (Antetokounmpo, Tymilianowicz) are valid corpus entries but realistically can't be formed from a 7-letter Bee — that's fine, they just won't appear in puzzles where their letters aren't on the board.
- Hyphens and apostrophes stripped for matching (so "O'Neal" → "ONEAL"). The displayed name keeps the punctuation.
- Diacritics normalized (Dončić → DONCIC).
- All matching is uppercase.

### Quality / contention

- Some names are *also* common English words (Hill, Wood, Brown, Smith, Bird). That's fine — they're valid Bee answers either way; the user just needs to think of them as names. The puzzle's pleasure is the dual-meaning click.
- Some names are *very* obscure (1980s journeyman bench players). Excluded from active corpus by a **fame floor** — we keep names that played at least 100 NBA games OR won at least one major award OR are currently on a roster. WNBA gets a less strict floor (3 seasons OR award OR currently active) since the league is younger and total game counts are lower. Currently-active rosters always pass — Wemby is in from day one. Tunable post-launch based on user signal.

---

## Daily puzzle generation

The center letter + 6 outer letters need to be picked such that:

1. There exist **enough valid names** in the corpus to make the puzzle satisfying (target: 12–25 valid names per puzzle, with at least 1 pangram)
2. The names span easy → hard (so casuals find a few, vets find more, hall-of-famers chase the pangram)
3. The center letter is a *meaningful constraint* — i.e., a letter that meaningfully filters the corpus. C, J, M, R, S, B, L, T are good centers. Q, X, Z are too restrictive; A, E, I, O are too permissive.

### Algorithm sketch

1. Pick a candidate center letter from `[B, C, D, F, G, H, J, K, L, M, N, P, R, S, T, W]` (the "good middle weight" set)
2. Find all corpus names that contain that center letter
3. Compute, for every distinct 7-letter set that includes this center letter, how many names from step 2 can be formed using only those 7 letters (with center required)
4. Pick a 7-letter set where the count lands in [12, 25] and at least one pangram exists
5. Score the resulting puzzle on a "spread" metric — too easy if everything is 4 letters; too hard if median is 8+. Aim for median around 5–6 letters.

This is deterministic given a daily seed. Slightly different problem from the crossword fill (set-cover instead of constraint-satisfaction), but well-trodden territory.

### Pre-computation vs daily

For v2 ship: pre-compute a year's worth of Bee puzzles in advance (cheap; runs offline once), commit them to `puzzles/<league>/bee/<date>.json`. Re-run when the corpus updates (quarterly). This sidesteps the need for a daily Bee cron and avoids the "what if the algorithm finds nothing?" failure mode.

---

## Tier system: Rookie → GOAT

NYT Bee uses 9 tiers from "Beginner" to "Queen Bee", with the threshold for each tier as a percentage of the *total possible score* on that puzzle.

User suggested: Rookie → Sophomore → Vet → All-Star → Champion → Hall of Famer → GOAT (7 tiers). I'd add 1–2 lower tiers so casuals see progress on their first 3–4 finds. Proposed 9-tier ladder:

| Tier | Threshold | Vibe |
|---|---|---|
| **Undrafted** | 0% (start state, before any names) | Show this as an invitation, not as a tier |
| **G League call-up** | 1% | First name found |
| **Rookie** | 5% | Established that you can play |
| **Sophomore** | 12% | Comfortable |
| **Vet** | 22% | Knows the league |
| **All-Star** | 35% | Among the best |
| **Champion** | 50% | Elite |
| **Hall of Famer** | 70% | All-time great |
| **GOAT** | 100% (every name found) | Mythical |

The 100% GOAT threshold is harder than NYT's "Queen Bee" — Queen Bee at NYT is the same percentile but on a much bigger word universe. Hoops names are smaller; 100% should be reachable but rare. If empirically too hard, drop to 95% in v2.5.

(NYT Bee shows the tier you're currently on plus the threshold for the next tier. We do the same — the next-tier nudge is part of what keeps you coming back at lunchtime.)

### Tier visualization

A vertical progress bar with tier markers, each labeled. The current tier name is the loudest typography on the page, second only to the puzzle. Crossing a tier triggers a small celebration (toast + pulse animation, no popup — popups break flow).

---

## Three flavors of /bee

| URL | Corpus | Use case |
|---|---|---|
| `/nba/bee` | NBA names only | A user who is NBA-loyal |
| `/wnba/bee` | WNBA names only | A user who is WNBA-loyal |
| `/bee` | Combined | A user who follows both leagues; also the cross-promotional default |

Naming is the puzzle's identity. `/nba/bee` reads as "the NBA Bee, today's puzzle"; the title on that page is "NBA Bee #N".

The combined `/bee` is its own daily puzzle, generated independently. Day-to-day there's no relationship between the three Bees — they pick their own letters.

---

## Visual identity

- **Hexagon palette:** match league color (NBA red center, neutral outer / WNBA orange center, neutral outer / combined `/bee`: a different neutral, maybe gold).
- **Type:** same Iowan/serif headers; tabular monospace for the score readout.
- **Layout:**
  - Top: title ("NBA Bee #N · May 21"), tier display
  - Middle: 7 hexagons in honeycomb arrangement
  - Below hexagons: entry bar (current word being formed)
  - Below entry: shuffle button + delete button + submit button
  - Below buttons: score, "Found N names" toggle, found-names list (collapsed by default)
  - Footer: same pattern as crossword — share, link to today's other games

### Mobile considerations

The hexagon layout needs to scale gracefully. NYT's Bee has an excellent mobile design — large tap targets, no hover states, the keyboard input stays out of the way. We mirror that. The entry bar needs to be reachable with a thumb on iPhone — top of viewport is wrong, middle/lower is right.

---

## Sharing

NYT Bee shares are minimal — just the tier achieved + date + score. We do the same:

```
NBA Bee #042 · May 21
🏆 Hall of Famer
38/52 names · 142 points
nbamini.app/nba/bee
```

The trophy emoji shifts based on tier (rookie 🌱, vet 🏀, all-star ⭐, champion 🏆, etc.). The found-names list is *not* shared — that's the spoiler floor.

---

## Schema

A separate JSON file format from the crossword (different shape entirely):

```json
{
  "date": "2026-05-21",
  "league": "nba",
  "bee_number": 42,
  "center_letter": "M",
  "outer_letters": ["A", "C", "K", "L", "O", "R"],
  "valid_names": ["MALONE", "MARCIULIONIS", "MCCOLLUM", ...],
  "pangrams": ["MCCOLLUM"],
  "tier_thresholds": {
    "g_league_callup": 1,
    "rookie": 8,
    "sophomore": 19,
    ...,
    "goat": 142
  },
  "max_score": 142,
  "generated_at": "2026-05-21T10:00:00Z"
}
```

The `valid_names` list is the answer key. The frontend can either (a) fetch it on submission for validation or (b) ship it inline at page load. Inline is simpler and the list is small (typical 12–25 names + their letter sets is a few KB). Inline it is.

(One concern: shipping the answer list inline means a determined user can View Source and "win" the Bee. NYT does the same thing and has decided it's not a meaningful problem. Same call here.)

---

## Storage and state

Per-Bee state lives in localStorage:

```
nba-mini-state.bee = {
  nba: {
    "2026-05-21": { found: ["MALONE", "MCCOLLUM"], score: 17 }
  },
  wnba: { ... },
  combined: { ... }
}
```

Idempotent — refreshing the page restores progress. Cross-device sync is a v3+ accounts feature.

Per-Bee streak — same rules as crossword: a "completed Bee day" is reaching at least Rookie tier (or some sane minimum, debatable). Per-league streaks. Skip days when no Bee was generated (we generate daily).

---

## Pipeline impact

The Bee corpus and Bee generator are largely independent of the crossword pipeline:

- New module: `nba_mini.bee` containing `corpus.py`, `generate_bee.py`, `tiers.py`
- New data files: `pipeline/data/names_nba.txt`, `pipeline/data/names_wnba.txt`
- New cron path (or extend daily-puzzle.yml with a Bee step) to generate the next-day Bee, since pre-computation isn't strictly daily — but we *do* want the schema to carry "today's puzzle for today" so the pre-computed-batch model is fine
- New schema validator on the frontend, mirroring the crossword schema's strictness

The Bee generator never calls Claude. It's pure deterministic algorithm against a static corpus. Operating cost ≈ $0 for the Bee.

(This is a notable contrast to the crossword's per-puzzle Anthropic spend. The Bee is essentially free to run.)

---

## Roadmap placement

**v3 — hoops Spelling Bee.** Lands after multi-league (v2). Why:

- We need a stable league system before we can have league-flavored Bees
- The Bee is genuinely additive — it doesn't blocking critical ritual
- The names corpus needs care; rushing it ships a janky v1 that loses the audience

If v2 is the right time to soft-launch a single-league Bee, that's a v2.5 conversation. The brainstorm explicitly does *not* commit either way.

### Within-v3 sequencing

If v3 is "Bee", here's the rough breakdown:

- **U1.** Names corpus — the data file + license/sourcing
- **U2.** Bee schema (Python + TypeScript)
- **U3.** Bee generator algorithm (offline, batch)
- **U4.** Bee frontend — hexagon component + entry bar + found-names list
- **U5.** Tier system + animations
- **U6.** Score calculation + share text
- **U7.** Mobile polish
- **U8.** Cross-promotional surfaces — link from crossword to today's Bee, link from Bee to today's crossword

---

## Open questions parked for the implementation plan

- **First names accepted, or only last names?** Default last names. Could expand to "well-known one-namers" (Magic, Kareem, Shaq, Sue) but that's a slippery slope. Plan-time decision.
- **Is the daily Bee actually generated daily, or is it a long pre-computed sequence we cycle through?** Pre-computed offers cost-zero ops. Daily-generated stays current with new draftees etc. Probably pre-computed for v3 launch with quarterly re-gen.
- **Combined `/bee` corpus — one big pool, or alternating days?** Default: one big pool. But "Today the combined Bee is NBA-skewed" might be a fun variant. Not v3 launch.
- **NYT Bee gets weekly difficulty modulation (Sundays harder).** Should we mirror that? Probably yes — Sundays are when fans have time. Could differentiate via "Hall of Famer Sundays" with smaller tier names.
- **Anti-spoiler concern of inline answer list.** NYT ships theirs inline; not their breaking concern. Keep ours inline.
- **Recently-retired players "fame floor."** Where does that line fall? Is JaVale McGee in the corpus? Is Jeremy Lin? Empirical question — start permissive, tighten if users complain about obscure names.
- **WNBA names corpus depth.** WNBA has fewer total players ever — does the corpus support a satisfying daily Bee? Probably yes (~1500 players in WNBA history vs ~5000 in NBA, both more than enough for daily 7-letter puzzles), but worth validating at plan time with a test run.
- **Hispanic / European players with ñ, ć, š diacritics.** Strip for matching (Doncic = DONCIC), preserve for display. Same convention NYT uses for accented letters.
- **The Center-letter difficulty calibration.** How often does Q/X/Z appear as a center? In NYT Bee these are rare-treat puzzles. We probably ship without them (more frustrating than fun for a 7-letter game with names) and add later as themed weeks.

---

## Sources & References

- Origin v0 brainstorm: [2026-05-15-nyt-nba-crossword-design.md](2026-05-15-nyt-nba-crossword-design.md)
- Sibling brainstorm same day: [2026-05-21-multi-league-wnba-design.md](2026-05-21-multi-league-wnba-design.md)
- NYT Spelling Bee for mechanic reference (we mirror the rules; we do not copy any code or data)
- `nba_api` for player roster source
- basketball-reference for historical roster source
