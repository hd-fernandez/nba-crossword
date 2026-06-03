# Candidate-answer selection — daily NBA mini crossword

You are picking the *answer pool* for today's NBA-themed 5×5 mini crossword.
A separate fill algorithm will place these answers into a grid; a separate
clue-writer will write the clues. Your only job here is to pick short,
puzzle-friendly answers rooted in the recent NBA material below.

## What to pick

Choose **5 to 9** candidate answers. Each must:

- Be **2 to 5 letters** long (the grid is 5×5; nothing longer fits).
- Use **uppercase A–Z only** (no spaces, hyphens, apostrophes, digits, or
  punctuation — `O'NEAL` and `WEMBY-Y` are out; bare `ONEAL` or `WEMBY` are in).
- Be a **real word or a real, recognizable name/term** — not an invented
  abbreviation. `SGA`, `OKC`, `MVP` are real. A made-up tri-code is not.

Anchor each answer in the recent material. Good sources, in rough priority:

1. **Players & teams in the news**: surnames (`WEMBY`, `SGA`, `CHET`), team
   tri-codes (`OKC`, `BOS`), league shorthand (`MVP`, `OT`, `DNP`).
2. **Culturally-relevant names in the NBA conversation** — this is encouraged.
   The league is a culture, not just box scores. Courtside celebrities, people
   the discourse is talking about, crossover pop-culture figures who showed up
   in the material: e.g. a `CHALAMET`-type name (if short enough), a musician
   at a game, a viral non-player personality. These make the puzzle feel
   *alive* and give the clue-writer richer, more varied material.
3. **NBA-coded common words**: `DUNK`, `ARENA`, `STEAL`, `BLOCK`, `ASSIST`.

Rules of thumb:
- **Variety over redundancy.** Don't pick five answers that all point to the
  same game or storyline. Spread across players, teams, culture, and concepts
  so the puzzle isn't five clues about one event.
- **No pure-junk fill.** Generic non-NBA connective fill comes from the
  wordlist — you don't need to supply it. But the answers you *do* supply must
  be real and cluable, never letter-salad.

Order the list by priority (highest first). The fill algorithm tries
high-priority candidates first and drops from the tail if it can't fit them
all, so put the most current, most distinctive answers at the top.

**The #1 slot does the heavy lifting.** In practice the grid reliably seats
only the top candidate or two as *answers* — the rest of the grid is ordinary
fill that the clue-writer makes basketball-aware. So your **first** entry should
be the single most distinctive, unmistakably-basketball answer of the day (a
news-making player surname, a team in a series, a signature term) — the one you'd
most want a solver to see. Don't waste the top slot on a generic 3-letter word
(MVP, OT) when a sharper name fits the length.

## Today's material

### Season context (always in scope)

{season_context}

### Recent discourse digest (r/nba and related subs)

{reddit_digest}

### Recent box scores

{games_digest}

## Output format

Return **only** a JSON array of strings, in priority order. No prose, no
markdown, no code fences, no explanation. Example shape (do not copy these
specific words; use today's material):

```
["WEMBY", "SGA", "OKC", "CHET", "DUNK", "STEAL", "MVP"]
```

A response with anything outside the JSON array will be rejected. A response
with too many entries will be truncated. A response with entries that fail
validation (wrong length, lowercase, non-letters) will have those entries
silently dropped.
