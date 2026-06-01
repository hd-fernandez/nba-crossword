/**
 * Fetcher for Bee puzzles. Mirrors the crossword's fetchPuzzle pattern.
 *
 * Storage path: /puzzles/<league>/bee/<date>.json. The 404 path returns
 * null so the page can show a "no Bee today" state without the fetch
 * itself throwing.
 */

import { parseBeePuzzle, type BeePuzzle, type BeeLeague } from "./bee";
import { todayInEastern } from "./puzzle";
import { z } from "zod";

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
export async function fetchLatestBee(
  league: BeeLeague,
  today: string = todayInEastern(),
  fetchImpl: typeof fetch = fetch,
): Promise<ResolvedBee | null> {
  const todays = await fetchBee(league, today, fetchImpl);
  if (todays) return { puzzle: todays, date: today, isToday: true };

  let fallbackDate: string | undefined;
  try {
    const res = await fetchImpl(`/puzzles/${league}/bee/index.json`, {
      cache: "no-store",
    });
    if (res.ok) {
      const parsed = BeeIndexSchema.safeParse(await res.json());
      if (parsed.success) {
        fallbackDate = parsed.data.dates
          .filter((d) => d <= today)
          .sort()
          .at(-1);
      }
    }
  } catch {
    return null;
  }
  if (!fallbackDate) return null;

  const fallback = await fetchBee(league, fallbackDate, fetchImpl);
  if (!fallback) return null;
  return { puzzle: fallback, date: fallbackDate, isToday: false };
}
