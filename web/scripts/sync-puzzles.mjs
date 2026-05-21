// Copies puzzles/<league>/*.json from the repo root into
// web/public/puzzles/<league>/ so Next.js can serve them as static assets at
// /puzzles/<league>/<date>.json.
//
// Why a copy step (not a symlink, not a rewrite):
// - Symlinks inside web/public are fragile across CI runners and Windows devs.
// - Next.js rewrites can't reach files outside the project root.
// - A tiny rsync-style copy is portable, idempotent, and runs as predev/prebuild.
//
// The pipeline writes new puzzles to repo-root /puzzles/<league>/. This script
// is the boundary that brings them into Next's static-asset world. Re-running
// is safe.

import { mkdirSync, readdirSync, copyFileSync, statSync, existsSync } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, "../../puzzles");
const DST = resolve(__dirname, "../public/puzzles");
const LEAGUES = ["nba", "wnba"];

if (!existsSync(SRC)) {
  console.warn(`[sync-puzzles] no source dir at ${SRC}, skipping`);
  process.exit(0);
}

mkdirSync(DST, { recursive: true });

let totalCopied = 0;
for (const league of LEAGUES) {
  const srcLeague = join(SRC, league);
  const dstLeague = join(DST, league);
  if (!existsSync(srcLeague)) continue;
  mkdirSync(dstLeague, { recursive: true });
  let copied = 0;
  for (const name of readdirSync(srcLeague)) {
    if (!name.endsWith(".json")) continue;
    const srcPath = join(srcLeague, name);
    const dstPath = join(dstLeague, name);
    if (!statSync(srcPath).isFile()) continue;
    copyFileSync(srcPath, dstPath);
    copied += 1;
  }
  console.log(`[sync-puzzles] ${league}: copied ${copied} file(s)`);
  totalCopied += copied;
}

console.log(`[sync-puzzles] total: ${totalCopied} puzzle file(s)`);
