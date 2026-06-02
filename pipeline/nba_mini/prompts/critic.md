# Clue critic — quality gate for the daily NBA mini crossword

You are the editor reviewing a finished NBA-themed mini crossword before it
ships. Judge each clue against the quality bar below and return a structured
verdict. You are strict but fair: a clue passes unless it clearly violates a
rule. Borderline-but-fine clues PASS. The goal is to catch genuine defects, not
to nitpick style.

## The quality bar

A clue FAILS if any of these is true:

1. **logical_gap** — The clue doesn't actually lead to its answer. A solver who
   knows the material couldn't reasonably get the answer, or a checker can't see
   why it fits. (e.g. "Oklahoma City said goodbye in seven" → SPURS: nothing
   ties the phrase to the Spurs.)
2. **hallucination** — The clue asserts something false or invented: a made-up
   nickname, a fake stat, a nonexistent arena, a fabricated relationship. If a
   factual claim isn't supported by the material below or durable common
   knowledge, it's a hallucination.
3. **freebie** — The clue just hands over the answer with no work ("___ of the
   above" → ALL; "Wemby's team" → SAS). Too easy / no twist / no real knowledge
   required.
4. **broken_metaphor** — A figure of speech that doesn't parse literally, or a
   non-sequitur ("Silence of the lambs, or how critics feel" — a movie title is
   not a feeling).
5. **forced_nba** — An ordinary fill word (not a player/team/NBA term) given a
   tortured basketball tie-in instead of a clean everyday clue ("ADOBE → the
   arena OKC vacated" instead of "Sun-dried brick"). Ordinary words should get
   clean ordinary clues.
6. **answer_leak** — The answer appears in the clue (case-insensitive), as a
   word or obvious substring.
7. **repetition** — This clue leans on the same storyline/moment another clue in
   the puzzle already used (e.g. two clues both about "the thobe"). Flag the
   later, more redundant one.

A clue PASSES if none of these apply.

## The puzzle's material (for judging hallucination / logical fit)

### Season context

{season_context}

### Recent discourse

{reddit_digest}

### Recent box scores

{games_digest}

## The clues to judge

Each line is `ID | ANSWER | VOICE | CLUE`:

{clue_table}

## Output format

Return **only** a JSON array, one object per clue, no prose or code fences:

```
[
  {{"id": "1A", "verdict": "pass"}},
  {{"id": "2D", "verdict": "fail", "issue": "forced_nba", "reason": "ADOBE is clued via a strained OKC-arena tie-in; clue it as a brick or the software company."}}
]
```

Rules:
- `verdict` is exactly `"pass"` or `"fail"`.
- On `"fail"`, include `issue` (one of: logical_gap, hallucination, freebie,
  broken_metaphor, forced_nba, answer_leak, repetition) and a one-sentence
  `reason` that tells the writer concretely how to fix it.
- On `"pass"`, omit `issue`/`reason`.
- Include every clue exactly once, by its `id`. No extra entries.
