/**
 * Fetcher for Bee puzzles. Mirrors the crossword's fetchPuzzle pattern.
 *
 * Storage path: /puzzles/<league>/bee/<date>.json. The 404 path returns
 * null so the page can show a "no Bee today" state without the fetch
 * itself throwing.
 */

import { parseBeePuzzle, type BeePuzzle, type BeeLeague } from "./bee";
import { todayInEastern } from "./puzzle";

export async function fetchBee(
  league: BeeLeague,
  date: string = todayInEastern(),
  fetchImpl: typeof fetch = fetch,
): Promise<BeePuzzle | null> {
  const res = await fetchImpl(`/puzzles/${league}/bee/${date}.json`, {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(
      `failed to fetch ${league} Bee for ${date}: HTTP ${res.status}`,
    );
  }
  const raw = await res.json();
  return parseBeePuzzle(raw);
}
