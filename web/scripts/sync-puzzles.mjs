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

function copyJsonFiles(srcDir, dstDir) {
  if (!existsSync(srcDir)) return 0;
  mkdirSync(dstDir, { recursive: true });
  let copied = 0;
  for (const name of readdirSync(srcDir)) {
    const srcPath = join(srcDir, name);
    if (!statSync(srcPath).isFile()) continue;
    if (!name.endsWith(".json")) continue;
    copyFileSync(srcPath, join(dstDir, name));
    copied += 1;
  }
  return copied;
}

let totalCopied = 0;
for (const league of LEAGUES) {
  // Crossword puzzles at puzzles/<league>/*.json
  const xword = copyJsonFiles(join(SRC, league), join(DST, league));
  // Bee puzzles at puzzles/<league>/bee/*.json
  const bee = copyJsonFiles(join(SRC, league, "bee"), join(DST, league, "bee"));
  console.log(`[sync-puzzles] ${league}: ${xword} crossword, ${bee} bee`);
  totalCopied += xword + bee;
}

console.log(`[sync-puzzles] total: ${totalCopied} puzzle file(s)`);
