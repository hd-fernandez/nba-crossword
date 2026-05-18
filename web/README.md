# web

Next.js 14 (App Router) PWA that serves the daily NBA Mini puzzle.

## Local dev

```bash
cd web
npm install
npm run dev
```

Visit `http://localhost:3000`.

## Tests

```bash
npm test
```

Vitest + happy-dom + Testing Library. Setup file: `tests/setup.ts`.

## Layout

- `app/` — App Router pages
- `components/` — React components (Grid, ClueBar, Timer, FinishScreen, Share, StreakBadge)
- `lib/` — domain helpers (puzzle parsing, share-grid generation, localStorage state)
- `public/` — manifest, icons, and (at build time) the puzzles directory
- `tests/` — Vitest suite
