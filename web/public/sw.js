/* eslint-disable no-restricted-globals */
/*
 * Service worker for The NBA Mini.
 *
 * Strategy:
 *   - App shell ("/", manifest, icons, built static assets): cache-first.
 *     Once cached, offline opens straight from cache. Bumping CACHE_VERSION
 *     evicts the old shell on the next deploy.
 *   - Daily puzzle JSON (/puzzles/*.json): network-first with cached fallback.
 *     The cron commits a new puzzle each morning; we want users to receive it
 *     within minutes of the deploy, but we also want offline play to keep
 *     working. Network success refreshes the cache; network failure falls back
 *     to whatever JSON we last saw.
 *   - Cross-origin requests are passed through untouched. The SW never
 *     intercepts e.g. analytics or third-party CDN calls.
 *   - Only GET requests are cached. POST/PUT/DELETE bypass the SW entirely.
 *
 * Cache busting:
 *   - Bump CACHE_VERSION on any meaningful change to this file or the shell
 *     contract. The activate handler deletes any cache whose name doesn't
 *     start with the current version prefix.
 */

const CACHE_VERSION = "nba-mini-v1";
const SHELL_CACHE = `${CACHE_VERSION}-shell`;
const PUZZLE_CACHE = `${CACHE_VERSION}-puzzles`;

// Minimum shell to make the app open offline. Next.js fingerprints its built
// assets, so we deliberately don't pre-list them here — they get cached on
// first fetch via the runtime cache-first path. The icons + manifest are
// stable URLs and worth pre-warming so the install UX works offline-first.
const SHELL_PRECACHE = [
  "/",
  "/manifest.webmanifest",
  "/icons/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) =>
        // addAll is atomic — if any URL fails, the whole cache.addAll rejects
        // and the SW won't install. Wrap each entry in a tolerant fetch so a
        // single missing asset (e.g., a renamed icon) doesn't brick the SW.
        Promise.all(
          SHELL_PRECACHE.map(async (url) => {
            try {
              const response = await fetch(url, { cache: "no-cache" });
              if (response.ok) {
                await cache.put(url, response);
              }
            } catch {
              // Swallow — best-effort precache.
            }
          }),
        ),
      ),
  );
  // Activate the new SW as soon as it's installed; combined with clients.claim
  // below, this means a deploy with a bumped CACHE_VERSION takes effect on the
  // next page load instead of waiting for every tab to close first.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => !key.startsWith(`${CACHE_VERSION}-`))
          .map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Daily puzzle JSON: network-first, cache as fallback.
  if (url.pathname.startsWith("/puzzles/") && url.pathname.endsWith(".json")) {
    event.respondWith(networkFirst(request, PUZZLE_CACHE));
    return;
  }

  // Don't cache the service worker itself — let the browser re-validate it
  // every load. (Vercel headers reinforce this; this is belt-and-suspenders.)
  if (url.pathname === "/sw.js") return;

  // App shell + built static assets: cache-first.
  event.respondWith(cacheFirst(request, SHELL_CACHE));
});

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) {
      // Clone before caching — body can only be consumed once.
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  // Only cache successful, basic (same-origin) responses to avoid poisoning
  // the cache with redirects or opaque entries.
  if (response.ok && response.type === "basic") {
    cache.put(request, response.clone());
  }
  return response;
}
