---
title: Service-worker cache-first served a stale dev shell — disable + self-heal in dev
date: 2026-06-01
category: solutions
module: web/lib/sw-register
problem_type: bug_pattern
component: frontend_pwa
severity: high
applies_when:
  - "A PWA registers a cache-first service worker and developers run a local dev server on the same origin"
  - "Pages 'never load on their own' and only refresh after a hard reload (cmd+shift+R)"
tags: [service-worker, pwa, cache, dev-environment, next-js]
---

# Service-worker cache-first served a stale dev shell

## Context

The app registers a service worker that caches the app shell cache-first (and
puzzle JSON network-first). In production that's correct — the shell is
immutable per deploy. But in local dev, every code change produces a new shell,
and the cache-first SW kept serving the *previous* shell from cache. The
symptom the user reported: **"I always always have to do cmd+shift+R on each tab
of each page. It never loads on its own."**

A normal reload re-requests the page, but the SW intercepts and answers from
cache before the network is consulted, so the new code never shows up. Only a
hard reload (which bypasses the SW) worked — and only until the next edit.

## Guidance

Two changes in [web/lib/sw-register.ts](../../web/lib/sw-register.ts):

1. **Don't register the SW in dev at all.** Gate registration on
   `process.env.NODE_ENV === "production"`. There is no value in a caching
   shell during development — only staleness.

2. **Self-heal: actively tear down any SW left over from a prod build on the
   same origin.** Disabling future registration isn't enough — a developer who
   ran a production build once has a live SW + populated caches that will
   outlive the flag. On dev load, unregister all registrations and delete all
   cache keys:

```ts
async function unregisterServiceWorkers(): Promise<void> {
  const registrations = await navigator.serviceWorker.getRegistrations();
  await Promise.all(registrations.map((r) => r.unregister()));
  if ("caches" in window) {
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => caches.delete(key)));
  }
}
```

The cleanup is wrapped in try/catch and only `console.warn`s on failure — a
dev-only convenience must never throw and break the page.

## Why This Matters

A cache-first SW is invisible until it isn't, and the failure mode ("stale page,
fixed by hard reload") reads like a hundred unrelated bugs. Developers burn
time blaming their own code, the bundler, or HMR. The root cause is that the SW
is doing exactly what it was told — answering from cache — in an environment
where that's never what you want.

The self-heal step is the non-obvious half. It costs one final hard reload per
tab (to load the cleanup code itself), after which the SW is gone for good in
dev. Without it, the flag silently does nothing for anyone who has ever run a
prod build locally.

## When to Apply

- Any PWA / Next.js app with a registered service worker, the moment a
  teammate reports "I have to hard-refresh to see my changes."
- Reach for this *before* suspecting HMR, the bundler cache, or browser disk
  cache — the SW intercepts ahead of all of them.

## Caveat (known residual)

The dev cleanup clears **all** caches on the origin on every dev load. If you
run a production-build smoke test on the same `localhost` origin, it loses its
SW/caches between reloads. Acceptable for now; if it ever bites, scope the
cleanup to the app's own cache key prefix.

## Related

- Commit: `73b8213` (disable SW in dev + self-heal)
- [Index + walk-back puzzle fallback](2026-06-01-index-walk-back-fallback.md) — the other half of the "page won't load" debugging session
