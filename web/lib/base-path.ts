/**
 * Deploy-location base path.
 *
 * Mirrors `basePath` in next.config.mjs. Next.js automatically prefixes the
 * URLs it controls — `<Link>`, the router, `next/font`, built `_next/*`
 * assets — with the configured basePath. But it does NOT touch the URLs we
 * build by hand: raw `fetch("/puzzles/...")` calls, CSS `background-image`
 * URLs, and the paths baked into the service worker / manifest. Those have to
 * be prefixed explicitly, and this is the single source of truth for doing so.
 *
 * Empty string by default, so root deploys (local dev, a future Vercel /
 * nbamini.app deploy) are byte-for-byte unchanged. The GitHub Pages build
 * sets NEXT_PUBLIC_BASE_PATH=/<repo> and every hand-built URL shifts with it.
 */
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/**
 * Prefix an absolute, app-root-relative path with the deploy base path.
 * Pass paths that start with "/" (e.g. "/puzzles/nba/index.json"). A no-op
 * when BASE_PATH is empty.
 */
export function withBasePath(path: string): string {
  return `${BASE_PATH}${path}`;
}
