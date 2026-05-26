/**
 * Share-text generator for the Bee.
 *
 * Mirrors the crossword's spoiler-free share approach: tier reached,
 * score, date — no answer leaks. The found-names list is deliberately
 * NOT shared.
 */

import { tierForScore, type BeePuzzle, type TierKey } from "./bee";

const TIER_LABELS: Record<TierKey, string> = {
  g_league_callup: "G League Call-Up",
  rookie: "Rookie",
  sophomore: "Sophomore",
  vet: "Vet",
  all_star: "All-Star",
  champion: "Champion",
  hall_of_famer: "Hall of Famer",
  goat: "GOAT",
};

const TIER_EMOJI: Record<TierKey, string> = {
  g_league_callup: "🌱",
  rookie: "🌱",
  sophomore: "📈",
  vet: "🏀",
  all_star: "⭐",
  champion: "🏆",
  hall_of_famer: "🏆",
  goat: "👑",
};

const LEAGUE_LABELS: Record<string, string> = {
  nba: "NBA",
  wnba: "WNBA",
  combined: "Hoops",
};

/** Pretty date: "May 26" from "2026-05-26". */
export function formatBeeDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(dt);
}

export interface BeeShareInput {
  puzzle: BeePuzzle;
  score: number;
  foundCount: number;
}

/**
 * Build the spoiler-free share string. Matches the visual shape of NYT
 * Bee shares: tier line, fraction line, attribution line, no answers.
 *
 * Example:
 *   NBA Bee #42 · May 26
 *   🏆 Hall of Famer
 *   38 / 52 names · 142 pts
 *   nbamini.app/nba/bee
 */
export function buildBeeShareText({
  puzzle,
  score,
  foundCount,
}: BeeShareInput): string {
  const leagueLabel = LEAGUE_LABELS[puzzle.league] ?? "Hoops";
  const date = formatBeeDate(puzzle.date);
  const tier = tierForScore(score, puzzle.tier_thresholds, puzzle.max_score);
  const tierLine = tier
    ? `${TIER_EMOJI[tier]} ${TIER_LABELS[tier]}`
    : "🌱 Undrafted";
  const path = puzzle.league === "combined" ? "/bee" : `/${puzzle.league}/bee`;
  return [
    `${leagueLabel} Bee #${puzzle.bee_number} · ${date}`,
    tierLine,
    `${foundCount} / ${puzzle.valid_names.length} names · ${score} pts`,
    `nbamini.app${path}`,
  ].join("\n");
}

/**
 * Web Share API with clipboard fallback. Returns a status the caller can
 * use to decide whether to render a "Copied!" confirmation.
 */
export async function shareOrCopyBee(text: string): Promise<"shared" | "copied" | "unsupported"> {
  if (typeof navigator === "undefined") return "unsupported";
  // Prefer the native share sheet on mobile / supported browsers.
  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ text });
      return "shared";
    } catch (err) {
      // User-cancelled share is an AbortError; rethrow so callers can
      // distinguish a user cancel from a missing API. Other errors fall
      // through to the clipboard path.
      if (err instanceof DOMException && err.name === "AbortError") {
        throw err;
      }
    }
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return "copied";
  }
  return "unsupported";
}
