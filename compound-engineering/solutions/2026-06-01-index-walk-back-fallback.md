---
title: index.json + walk-back fallback so a static app never shows a dead page when content exists
date: 2026-06-01
category: solutions
module: web/lib/puzzle + web/lib/bee-fetch + web/scripts/sync-puzzles
problem_type: design_pattern
component: frontend
severity: high
applies_when:
  - "Serving dated content as static files (no server-side directory listing) and 'today' may be missing"
  - "You want graceful degradation to the most recent available item instead of a dead 'nothing here' page"
tags: [static-hosting, fallback, graceful-degradation, index, zod]
---

# index.json + walk-back fallback

## Context

Puzzles are served as static files at `/puzzles/<league>/<date>.json`. When
today's file doesn't exist (off-day, cron lag, or a local demo with no cron),
the page showed a dead "no puzzle today" state — even though plenty of older
puzzles were sitting right there. On a static host there's no directory
listing to discover them, so the client had no way to find the next-best file.

## Guidance

**Publish a manifest.** `sync-puzzles.mjs` (which copies repo-root puzzles into
`web/public` on predev/prebuild) also writes a per-directory `index.json`:

```json
{ "dates": ["2026-06-01", "2026-05-30", "..."], "latest": "2026-06-01" }
```

**Resolve with a walk-back, not a single guess.** `fetchLatestPuzzle` /
`fetchLatestBee`:

1. Try today's dated file. If present, return it with `isToday: true`.
2. Otherwise read the index, filter to dates `<= today`, sort newest-first,
   and **walk them in order, fetching each until one resolves.** Return the
   first hit with `isToday: false`.
3. Return `null` only when every candidate fails.

```ts
const candidates = index.dates.filter((d) => d <= today).sort().reverse();
for (const date of candidates) {
  const hit = await fetchPuzzle(league, date, fetchImpl);
  if (hit) return { puzzle: hit, date, isToday: false };
}
return null;
```

**Parse the index defensively and loudly.** Validate with a Zod schema and
`safeParse`. A malformed index returns `null` (treated as "no fallback") — but
**`console.warn` the parse error** so a corrupt manifest is distinguishable
from a legitimate 404, instead of silently collapsing.

## Why This Matters

The first instinct is to trust the manifest's newest entry and fetch exactly
that one file. That reintroduces the dead-page bug in a narrower form: if the
newest indexed file 404s (index/file skew, deploy race, a pruned file), you're
back to a dead page *while older puzzles still exist in the same index*. A code
review caught this exact regression — the single-shot `.at(-1)` version had
shipped. The fix is to walk the candidates, so a skewed index degrades to the
next file instead of to nothing.

`isToday` is the load-bearing distinction downstream: only the genuine absence
of *today's* file should affect streak/off-day logic; serving a fallback must
not. Keep that boolean honest at the resolution layer.

## When to Apply

- Any static-hosted app serving dated/sequential content where the newest item
  may be temporarily missing.
- Whenever you catch yourself fetching "the latest" by trusting a single
  manifest pointer — make it a walk, the failure modes are cheap to hit.

## Examples

**Index/file skew test (the regression guard):** index lists
`[D, D-1, D-2]` but `D.json` 404s. A correct resolver returns `D-1`; the
single-shot version returns `null`. Cover this explicitly.

## Related

- Commits: `73b8213` (index + fetchLatest), `740bc1d` (walk-back fix + warn on malformed index)
- [Publish vs slate date](2026-06-01-publish-vs-slate-date.md) — why "today" is often legitimately missing
- [Service-worker dev staleness](2026-06-01-service-worker-dev-staleness.md) — the other half of the same "page won't load" investigation
