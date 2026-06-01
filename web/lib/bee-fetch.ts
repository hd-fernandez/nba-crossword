/**
 * Fetcher for Bee puzzles. Mirrors the crossword's fetchPuzzle pattern.
 *
 * Storage path: /puzzles/<league>/bee/<date>.json. The 404 path returns
 * null so the page can show a "no Bee today" state without the fetch
 * itself throwing.
 */

import { parseBeePuzzle, type BeePuzzle, type BeeLeague } from "./bee";
import { todayInEastern } from "./puzzle";
import { withBasePath } from "./base-path";
import { z } from "zod";

export async function fetchBee(
  league: BeeLeague,
  date: string = todayInEastern(),
  fetchImpl: typeof fetch = fetch,
): Promise<BeePuzzle | null> {
  const res = await fetchImpl(withBasePath(`/puzzles/${league}/bee/${date}.json`), {
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

const BeeIndexSchema = z.object({
  dates: z.array(z.string().regex(/^\d{4}-\d{2}-\d{2}$/)),
  latest: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(),
});

export interface ResolvedBee {
  puzzle: BeePuzzle;
  date: string;
  isToday: boolean;
}

/**
 * Fetch the Bee to display: today's if present, else the most recent one
 * (per the per-league index written by sync-puzzles). Mirrors
 * {@link fetchLatestPuzzle} so the Bee never shows a dead "no Bee today"
 * page when real Bees exist. Returns null only when the league has none.
 */
async function fetchBeeIndexDates(
  league: BeeLeague,
  fetchImpl: typeof fetch,
): Promise<string[]> {
  try {
    const res = await fetchImpl(withBasePath(`/puzzles/${league}/bee/index.json`), {
      cache: "no-store",
    });
    if (!res.ok) return [];
    const parsed = BeeIndexSchema.safeParse(await res.json());
    if (!parsed.success) {
      // A malformed index is an operational problem, not a normal 404. Warn so
      // it's debuggable instead of silently collapsing to "no fallback."
      console.warn(`[bee-fetch] malformed ${league} bee index.json`, parsed.error);
      return [];
    }
    return parsed.data.dates;
  } catch {
    return [];
  }
}

export async function fetchLatestBee(
  league: BeeLeague,
  today: string = todayInEastern(),
  fetchImpl: typeof fetch = fetch,
): Promise<ResolvedBee | null> {
  const todays = await fetchBee(league, today, fetchImpl);
  if (todays) return { puzzle: todays, date: today, isToday: true };

  const dates = await fetchBeeIndexDates(league, fetchImpl);
  // Candidate fallbacks: every non-future date, newest first. Walk them in
  // order rather than trusting only the newest — if the newest indexed file
  // 404s (index/file skew, deploy race, a pruned file) we fall through to the
  // next instead of collapsing to a dead "no Bee" page while older Bees exist.
  const candidates = dates
    .filter((d) => d <= today)
    .sort()
    .reverse();
  for (const date of candidates) {
    const fallback = await fetchBee(league, date, fetchImpl);
    if (fallback) return { puzzle: fallback, date, isToday: false };
  }
  return null;
}
