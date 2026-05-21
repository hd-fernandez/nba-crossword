/**
 * Per-league configuration for the multi-league frontend.
 *
 * Everything that varies between NBA and WNBA — title, palette, hero photo,
 * prose copy — lives here. The page components consume this object; nothing
 * about the league should be hardcoded outside of this file plus the
 * route-level component selection.
 */

import type { League } from "./puzzle";

export interface LeagueTheme {
  /** The hex value used for the Start button, primary CTAs, accent text. */
  accent: string;
  /** Soft tint of the accent for shadows / glows under buttons. */
  accentShadow: string;
  /** Gradient overlay color stops on top of the hero photo (top → bottom). */
  overlayGradient: string;
}

export interface LeagueConfig {
  league: League;
  /** Display title shown in the page header. */
  title: string;
  /** Title used on the splash card (`<league> Mini #N`). */
  splashTitlePrefix: string;
  /** Path to the hero background photo (relative to /public). */
  heroPhoto: string;
  /** Short copy for the dormant state when no games yesterday. */
  noPuzzleCopy: string;
  theme: LeagueTheme;
}

const NBA: LeagueConfig = {
  league: "nba",
  title: "The NBA Mini",
  splashTitlePrefix: "NBA Mini",
  heroPhoto: "/bg/nba/players-on-court.jpg",
  noPuzzleCopy:
    "There were no NBA games yesterday. Streaks pause on off-days — see you tomorrow.",
  theme: {
    accent: "#c8102e",
    accentShadow: "rgba(200, 16, 46, 0.35)",
    overlayGradient:
      "linear-gradient(180deg, rgba(10,10,12,0.78) 0%, rgba(10,10,12,0.86) 60%, rgba(10,10,12,0.92) 100%)",
  },
};

const WNBA: LeagueConfig = {
  league: "wnba",
  title: "The WNBA Mini",
  splashTitlePrefix: "WNBA Mini",
  heroPhoto: "/bg/wnba/spalding.jpg",
  noPuzzleCopy:
    "There were no WNBA games yesterday. Streaks pause on off-days — see you tomorrow.",
  theme: {
    // WNBA orange — sits between official WNBA `#e87722` and a slightly
    // warmer tone that reads better against the dark gradient.
    accent: "#ff6b1a",
    accentShadow: "rgba(255, 107, 26, 0.4)",
    // Slightly warmer tint than NBA — the gradient is still mostly dark
    // but leans amber to support the orange palette.
    overlayGradient:
      "linear-gradient(180deg, rgba(20,12,8,0.78) 0%, rgba(20,12,8,0.86) 60%, rgba(20,12,8,0.94) 100%)",
  },
};

export const LEAGUE_CONFIGS: Record<League, LeagueConfig> = {
  nba: NBA,
  wnba: WNBA,
};

export function configFor(league: League): LeagueConfig {
  return LEAGUE_CONFIGS[league];
}

export const ALL_LEAGUES: League[] = ["nba", "wnba"];

export function otherLeague(league: League): League {
  return league === "nba" ? "wnba" : "nba";
}

/**
 * The "in-season" league for a given date — used as the cold-start default
 * when a brand-new visitor (no `lastPlayedLeague`) lands at `/`.
 *
 * Rules:
 * - Oct → Apr: NBA (regular + playoffs)
 * - May → Sep: WNBA (regular + playoffs)
 *
 * The May overlap month favors NBA because at v2 launch the audience is
 * still NBA-tilted; we route brand-new visitors there. Existing visitors
 * (with a `lastPlayedLeague`) ignore this entirely.
 */
export function inSeasonLeague(date: Date = new Date()): League {
  const m = date.getUTCMonth(); // 0-indexed
  // Oct(9), Nov(10), Dec(11), Jan(0), Feb(1), Mar(2), Apr(3) → NBA
  // May(4), Jun(5), Jul(6), Aug(7), Sep(8) → WNBA
  if (m >= 4 && m <= 8) return "wnba";
  return "nba";
}
