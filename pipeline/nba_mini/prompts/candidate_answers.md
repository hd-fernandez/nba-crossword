# Candidate-answer selection — daily NBA mini crossword

You are picking the *answer pool* for today's NBA-themed 5×5 mini crossword.
A separate fill algorithm will place these answers into a grid; a separate
clue-writer will write the clues. Your only job here is to pick short,
puzzle-friendly words rooted in yesterday's NBA material.

## What to pick

Choose **5 to 9** candidate answers. Each must:

- Be **2 to 5 letters** long (the grid is 5×5; nothing longer fits).
- Use **uppercase A–Z only** (no spaces, hyphens, apostrophes, digits, or
  punctuation — `O'NEAL` and `WEMBY-Y` are out; bare `ONEAL` or `WEMBY` are in).
- Anchor in the day's material: a player surname, team tri-code, league
  shorthand (e.g. `OT`, `MVP`, `DNP`), an NBA-coded common word (e.g. `ARENA`,
  `DUNK`, `STAR`), or a slang token from the discourse (e.g. `COOKED`).
- Skip easy stuff that has nothing to do with the NBA — generic fill words
  belong in the wordlist, not the candidate pool.

Order the list by priority (highest first). The fill algorithm tries
high-priority candidates first and drops from the tail if it can't fit them
all, so put the most NBA-flavored, most "of yesterday" answers at the top.

## Today's material

### Season context (always in scope)

{season_context}

### Yesterday's discourse digest (r/nba)

{reddit_digest}

### Yesterday's box scores

{games_digest}

## Output format

Return **only** a JSON array of strings, in priority order. No prose, no
markdown, no code fences, no explanation. Example shape (do not copy these
specific words; use today's material):

```
["WEMBY", "STEPH", "OT", "LAL", "ARENA", "DUNK", "STAR"]
```

A response with anything outside the JSON array will be rejected. A response
with too many entries will be truncated. A response with entries that fail
validation (wrong length, lowercase, non-letters) will have those entries
silently dropped.
