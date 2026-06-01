/** @type {import('next').NextConfig} */

// Deploy-location awareness.
//
// The app is built to live at the site root (local dev, and a future
// Vercel / nbamini.app deploy). GitHub Pages, however, serves a project
// repo from a subpath (https://<user>.github.io/<repo>/), so the build
// for Pages needs every absolute URL prefixed with that subpath.
//
// Both are driven by a single env var, empty by default:
//   - NEXT_PUBLIC_BASE_PATH unset  -> root deploy, identical to before.
//   - NEXT_PUBLIC_BASE_PATH=/repo  -> subpath deploy (the Pages workflow
//     sets this). Next rewrites its own asset/route URLs via basePath +
//     assetPrefix; our raw fetch()/asset paths use the same value through
//     lib/base-path.ts so they stay in lockstep.
//
// NEXT_OUTPUT_EXPORT=1 switches on the fully static export (`out/`), which
// is what Pages serves. Left off locally so `next dev` / `next start` keep
// their normal server behavior.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const isExport = process.env.NEXT_OUTPUT_EXPORT === "1";

const nextConfig = {
  reactStrictMode: true,
  ...(isExport ? { output: "export" } : {}),
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
  // Static export can't use the Next image optimizer (no server at runtime).
  // We only use plain CSS background-image today, but set this so an export
  // build never fails if a next/image is added later.
  images: { unoptimized: true },
  // Pages serves /<repo>/foo as /<repo>/foo/index.html; trailing slashes keep
  // relative asset resolution and deep links consistent under a subpath.
  ...(isExport ? { trailingSlash: true } : {}),
};

export default nextConfig;
