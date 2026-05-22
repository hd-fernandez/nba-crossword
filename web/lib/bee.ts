/**
 * Canonical Bee puzzle schema, mirrored from pipeline/nba_mini/bee/schema.py.
 *
 * Same shape, same invariants. Strict mode (no unknown keys), zod validates
 * structural rules, a `superRefine` block enforces the cross-field rules
 * (every name uses center, only board letters, pangrams hit all 7).
 */

import { z } from "zod";

export const BEE_LEAGUES = ["nba", "wnba", "combined"] as const;
export const BeeLeagueSchema = z.enum(BEE_LEAGUES);
export type BeeLeague = z.infer<typeof BeeLeagueSchema>;

export const TIER_KEYS = [
  "g_league_callup",
  "rookie",
  "sophomore",
  "vet",
  "all_star",
  "champion",
  "hall_of_famer",
  "goat",
] as const;
export type TierKey = (typeof TIER_KEYS)[number];

const tierField = z.number().min(0).max(100);

export const TierThresholdsSchema = z
  .object({
    g_league_callup: tierField,
    rookie: tierField,
    sophomore: tierField,
    vet: tierField,
    all_star: tierField,
    champion: tierField,
    hall_of_famer: tierField,
    goat: tierField,
  })
  .strict()
  .superRefine((t, ctx) => {
    const values = TIER_KEYS.map((k) => t[k]);
    for (let i = 1; i < values.length; i++) {
      if (values[i] < values[i - 1]) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `tier thresholds must be ascending; ${TIER_KEYS[i]}(${values[i]}) < ${TIER_KEYS[i - 1]}(${values[i - 1]})`,
        });
        return;
      }
    }
    if (values[values.length - 1] !== 100) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `top tier (goat) must be 100; got ${values[values.length - 1]}`,
      });
    }
  });
export type TierThresholds = z.infer<typeof TierThresholdsSchema>;

const RawBeePuzzleSchema = z
  .object({
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    league: BeeLeagueSchema,
    bee_number: z.number().int().min(1),
    center_letter: z.string().regex(/^[A-Z]$/),
    outer_letters: z.array(z.string().regex(/^[A-Z]$/)),
    valid_names: z.array(z.string()),
    pangrams: z.array(z.string()),
    tier_thresholds: TierThresholdsSchema,
    max_score: z.number().int().min(1),
    generated_at: z.string().datetime({ offset: true }),
  })
  .strict();

export const BeePuzzleSchema = RawBeePuzzleSchema.superRefine((p, ctx) => {
  // Outer letters: 6, distinct, none equal to center.
  if (p.outer_letters.length !== 6) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: `outer_letters must have 6 entries; got ${p.outer_letters.length}`,
    });
    return;
  }
  if (p.outer_letters.includes(p.center_letter)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: `center_letter '${p.center_letter}' cannot also appear in outer_letters`,
    });
    return;
  }
  if (new Set(p.outer_letters).size !== 6) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "outer_letters must be distinct (no duplicates)",
    });
    return;
  }

  const board = new Set([p.center_letter, ...p.outer_letters]);

  // Every valid_name uses center, uses only board letters, is uppercase A-Z.
  for (const name of p.valid_names) {
    if (!name) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "valid_names contains an empty entry",
      });
      return;
    }
    if (!/^[A-Z]+$/.test(name)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `valid_names entry '${name}' is not uppercase A-Z`,
      });
      return;
    }
    if (!name.includes(p.center_letter)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `valid_names entry '${name}' does not use the center letter '${p.center_letter}'`,
      });
      return;
    }
    for (const ch of name) {
      if (!board.has(ch)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `valid_names entry '${name}' uses letter '${ch}' not on the board`,
        });
        return;
      }
    }
  }

  // Pangrams: subset of valid_names, each uses every board letter.
  const validSet = new Set(p.valid_names);
  for (const pg of p.pangrams) {
    if (!validSet.has(pg)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `pangram '${pg}' is not in valid_names`,
      });
      return;
    }
    const used = new Set(pg);
    if (used.size !== board.size || ![...board].every((ch) => used.has(ch))) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `pangram '${pg}' does not use all 7 letters of the board`,
      });
      return;
    }
  }
});

export type BeePuzzle = z.infer<typeof BeePuzzleSchema>;

export function parseBeePuzzle(raw: unknown): BeePuzzle {
  return BeePuzzleSchema.parse(raw);
}

/**
 * Tier the user has reached given an integer score and the puzzle's
 * thresholds + max_score. Returns the highest tier whose threshold-as-points
 * is ≤ score, or null if even the lowest tier hasn't been hit yet.
 */
export function tierForScore(
  score: number,
  thresholds: TierThresholds,
  maxScore: number,
): TierKey | null {
  let current: TierKey | null = null;
  for (const key of TIER_KEYS) {
    const pointsThreshold = (thresholds[key] / 100) * maxScore;
    if (score >= pointsThreshold) {
      current = key;
    } else {
      break;
    }
  }
  return current;
}

/**
 * Score a name per the standard NYT Bee rule:
 *   - 4 letters = 1 point
 *   - each additional letter = +1 point
 *   - pangram = letter count + 7
 */
export function scoreName(name: string, isPangram: boolean): number {
  const len = name.length;
  if (len < 4) return 0;
  const base = len === 4 ? 1 : len;
  return isPangram ? base + 7 : base;
}
