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

import {
  mkdirSync,
  readdirSync,
  copyFileSync,
  statSync,
  existsSync,
  writeFileSync,
} from "node:fs";
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

// A puzzle filename is a bare ISO date: 2026-05-29.json. We index only those,
// not example.json or any future index.json, so the manifest is a clean list
// of real dated puzzles.
const DATED_JSON_RE = /^\d{4}-\d{2}-\d{2}\.json$/;

function copyJsonFiles(srcDir, dstDir) {
  if (!existsSync(srcDir)) return { copied: 0, dates: [] };
  mkdirSync(dstDir, { recursive: true });
  let copied = 0;
  const dates = [];
  for (const name of readdirSync(srcDir)) {
    const srcPath = join(srcDir, name);
    if (!statSync(srcPath).isFile()) continue;
    if (!name.endsWith(".json")) continue;
    copyFileSync(srcPath, join(dstDir, name));
    copied += 1;
    if (DATED_JSON_RE.test(name)) dates.push(name.replace(/\.json$/, ""));
  }
  return { copied, dates };
}

// Write an index.json listing available puzzle dates, newest first. The
// frontend reads this to fall back to the latest puzzle when there's no
// puzzle for *today* (e.g. an off-day, or the daily cron lagging) — so the
// app never shows a dead "no puzzle" page when real puzzles exist.
function writeIndex(dstDir, dates) {
  mkdirSync(dstDir, { recursive: true });
  const sorted = [...dates].sort().reverse(); // ISO dates sort lexically
  writeFileSync(
    join(dstDir, "index.json"),
    JSON.stringify({ dates: sorted, latest: sorted[0] ?? null }, null, 2) + "\n",
  );
}

let totalCopied = 0;
for (const league of LEAGUES) {
  // Crossword puzzles at puzzles/<league>/*.json
  const xword = copyJsonFiles(join(SRC, league), join(DST, league));
  writeIndex(join(DST, league), xword.dates);
  // Bee puzzles at puzzles/<league>/bee/*.json
  const bee = copyJsonFiles(join(SRC, league, "bee"), join(DST, league, "bee"));
  writeIndex(join(DST, league, "bee"), bee.dates);
  console.log(
    `[sync-puzzles] ${league}: ${xword.copied} crossword, ${bee.copied} bee`,
  );
  totalCopied += xword.copied + bee.copied;
}

console.log(`[sync-puzzles] total: ${totalCopied} puzzle file(s)`);
