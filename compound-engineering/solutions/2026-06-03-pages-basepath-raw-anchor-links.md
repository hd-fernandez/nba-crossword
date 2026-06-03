---
title: "GitHub Pages 404 on internal links: raw <a href> skips Next's basePath"
date: 2026-06-03
category: solutions
module: web
problem_type: ui_bug
component: frontend
symptoms:
  - "Clicking an in-app nav link shows GitHub's 'There isn't a GitHub Pages site here' 404"
  - "Some routes work (home -> league) while others 404 (the Bee tab)"
  - "The page itself exists in the static export — only the link to it is broken"
root_cause: wrong_api
resolution_type: code_fix
severity: high
tags: [nextjs, github-pages, basepath, static-export, routing, links]
---

# GitHub Pages 404: raw `<a href>` doesn't get Next's basePath

## Problem

On the GitHub Pages deploy (served from the subpath `/nba-crossword/`), the
in-app "Bee" tab 404'd with GitHub's own *"There isn't a GitHub Pages site
here"* page. The crossword pages and the home→league redirect worked fine, so it
looked route-specific. The Bee pages were actually built and present in the
export — only the **link** to them was wrong.

## Symptoms

- "Bee" tab (and the cross-league chip) → GitHub 404.
- Home→league nav and the NBA/WNBA pill toggle → fine.
- `out/nba/bee/index.html` existed in the static export the whole time.

## What Didn't Work

- Suspecting the static export wasn't emitting the Bee pages. It was — the build
  log listed `/nba/bee` and `/wnba/bee`, and the HTML files were in `out/`.

## Solution

Next.js auto-prefixes the configured `basePath` onto the URLs **it controls** —
`<Link>`, the router (`router.push/replace`), `next/font`, built `_next/*`
assets. It does **NOT** touch URLs you write by hand: plain `<a href>`, raw
`fetch()`, CSS `background-image`. Those must be prefixed explicitly.

The working links used `<Link>` / the router (auto-prefixed). The broken ones
were hand-written `<a href={`/${league}/bee`}>` — on Pages that resolves to
`github.io/nba/bee` (outside the `/nba-crossword/` subpath) → 404.

Fix: wrap each internal raw href in the repo's `withBasePath()` helper
(`web/lib/base-path.ts`), the single source of truth that mirrors
`next.config.mjs`'s `basePath`:

```tsx
// before — 404s on Pages
<a href={`/${league}/bee`}>
// after
<a href={withBasePath(`/${league}/bee`)}>
```

Three links fixed: the Bee chip + cross-league chip in `PuzzlePage.tsx`, the
back-link in `BeePage.tsx`. `LeagueToggle` was already correct because it uses
`<Link>` — do NOT wrap a `<Link href>` in `withBasePath()`, that double-prefixes
to `/nba-crossword/nba-crossword/...`.

## Why This Works

`withBasePath` prepends `NEXT_PUBLIC_BASE_PATH` (`/nba-crossword` on Pages, empty
on root/Vercel deploys), so hand-built URLs shift in lockstep with the ones Next
manages. Empty base path = byte-for-byte no-op locally.

## Prevention

- **Default to `<Link>` for internal navigation.** It handles basePath, prefetch,
  and client routing for free. Reach for `<a>` only when you specifically need a
  plain anchor — and then you own the basePath.
- For any hand-written internal URL (`<a href>`, `fetch`, CSS asset), pass it
  through `withBasePath()`. Grep before shipping: `grep -rn 'href={`/' web/` and
  `grep -rn 'href="/' web/` surface raw anchors; check each is `<Link>` (fine) or
  wrapped (fine).
- **Smoke-test the subpath build, not just `next dev`.** Root dev hides every
  basePath bug. Run `NEXT_PUBLIC_BASE_PATH=/nba-crossword NEXT_OUTPUT_EXPORT=1
  npm run build`, then grep the emitted HTML for the prefix:
  `grep -o 'href="[^"]*bee[^"]*"' out/nba/index.html` should show
  `/nba-crossword/nba/bee`.

## Related Issues

- `web/lib/base-path.ts` — the helper + the canonical explanation of what Next
  does and doesn't prefix.
