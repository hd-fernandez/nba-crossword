# web

Next.js 16 (App Router) PWA that serves the daily NBA Mini puzzle.

## Local dev

```bash
cd web
npm install
npm run dev
```

Visit `http://localhost:3000`.

The `predev` and `prebuild` hooks run `scripts/sync-puzzles.mjs`, which copies
repo-root `puzzles/*.json` into `public/puzzles/` so Next can serve them as
static assets at `/puzzles/<date>.json`.

## Tests

```bash
npm test
```

Vitest + happy-dom + Testing Library. Setup file: `tests/setup.ts`.

## Layout

- `app/` — App Router pages
- `components/` — React components (Grid, ClueBar, Timer, FinishScreen, Share, StreakBadge, SwRegister)
- `lib/` — domain helpers (puzzle parsing, share-grid generation, localStorage state, sw registration)
- `public/` — manifest, icons, service worker, and (at build time) the puzzles directory
- `tests/` — Vitest suite

## PWA

The app is installable as a Progressive Web App.

- **Manifest:** `public/manifest.webmanifest` (linked via `app/layout.tsx`'s
  `metadata.manifest`).
- **Service worker:** `public/sw.js`, registered on mount by
  `<SwRegister />` (see `lib/sw-register.ts`).
  - App shell + built static assets: cache-first.
  - `/puzzles/*.json`: network-first with cached fallback (so a freshly
    committed puzzle reaches users within minutes, but offline play still
    works against the last-cached puzzle).
  - Bump `CACHE_VERSION` in `public/sw.js` to evict old caches on deploy.
- **Icons:** `public/icons/icon.svg` is a placeholder. Drop in
  `icon-192.png`, `icon-512.png`, and `apple-touch-icon.png` (180×180) before
  public launch — see `public/icons/README.md`.

## Deployment (Vercel)

The site deploys to Vercel out of this `web/` subdirectory. The repo is a
monorepo (`pipeline/` + `web/`); Vercel only needs the `web/` half.

### First-time setup

1. In the Vercel dashboard, **import the GitHub repo**.
2. **Root Directory:** set to `web` (not the repo root). This is the single
   most important setting — without it Vercel will try to build from the
   repo root and fail.
3. **Framework Preset:** Vercel auto-detects Next.js. Leave as-is.
4. **Build Command:** leave default (`next build`). Our `prebuild` hook runs
   automatically and syncs the latest `puzzles/*.json` into the build.
5. **Install Command:** default `npm install`.
6. **Output Directory:** default (`.next`).
7. **Environment variables:** none required for v0. The frontend makes no
   server-side API calls.
8. **Production Branch:** `main`.

`vercel.json` (committed alongside this README) sets:

- `Cache-Control: public, max-age=0, must-revalidate` on `/sw.js` (so a new
  service worker is always picked up).
- `Service-Worker-Allowed: /` on `/sw.js` (lets the SW control the whole
  origin even if served from a sub-path in some edge config).
- `Cache-Control: public, max-age=300, stale-while-revalidate=3600` on
  `/puzzles/*.json` (so a freshly committed daily puzzle propagates in ~5
  minutes while the CDN keeps a stale copy hot).
- `Content-Type: application/manifest+json` on `/manifest.webmanifest`.

### Daily puzzle propagation

The GitHub Actions cron (`.github/workflows/daily-puzzle.yml`) commits a new
`puzzles/<date>.json` to `main` each morning. Vercel's GitHub integration
automatically rebuilds and deploys on every push to `main`, so the new
puzzle is live within a few minutes of the commit. No manual step.

### First-deploy smoke checklist

After the first deploy:

- [ ] `https://<project>.vercel.app/` loads and shows today's puzzle (or the
      "no puzzle today" state if there were no NBA games yesterday).
- [ ] `https://<project>.vercel.app/puzzles/example.json` returns the
      reference puzzle JSON.
- [ ] `https://<project>.vercel.app/manifest.webmanifest` returns the
      manifest with `Content-Type: application/manifest+json`.
- [ ] `https://<project>.vercel.app/sw.js` returns the service worker with
      `Cache-Control: public, max-age=0, must-revalidate`.
- [ ] DevTools → Application → Service Workers shows `sw.js` registered and
      activated.
- [ ] DevTools → Application → Manifest shows the manifest parsed without
      warnings (icon SVG may show a maskability warning until raster icons
      land — acceptable for v0).
- [ ] iOS Safari "Add to Home Screen" works (icon may be a screenshot until
      `apple-touch-icon.png` lands).
- [ ] Lighthouse → PWA audit passes the installability checks.

### Custom domain

Out of scope for v0. Free `*.vercel.app` is fine to start; add a custom
domain in Vercel project settings → Domains when ready.
