/**
 * localStorage-backed user state for the Mini.
 *
 * Single key (`STORAGE_KEY`), JSON-serialized. Per-league streaks live under
 * `leagues.<league>` so a v2 user with separate NBA + WNBA streaks doesn't
 * collide. The shape is version-tagged so future changes either migrate
 * forward or reset cleanly.
 *
 * Streak rule (per the v0 plan, U12, applied per league at v2):
 *   - completion = streak day
 *   - off-days (no puzzle existed in that league) skip; they neither break
 *     nor extend
 *   - missed *puzzle* days break the streak
 *   - no grace mechanic
 *
 * All read/write operations route through {@link loadState} / {@link saveState},
 * which gracefully degrade when `localStorage` is unavailable (SSR, private
 * mode, sandboxed iframes) or when the stored JSON is malformed. The pure
 * helpers ({@link recordCompletion}, {@link markOffDay}, {@link computeStreak},
 * etc.) operate on plain `Storage` objects so they're fully unit-testable
 * without any DOM stub.
 */

import type { League } from "./puzzle";

export const STORAGE_KEY = "nba-mini-state";
export const SCHEMA_VERSION = 2 as const;

export interface Settings {
  /** Future-proofing for U13's persistent "hide timer" toggle. */
  timerHidden?: boolean;
}

export interface LeagueState {
  /** ISO YYYY-MM-DD strings, sorted ascending, deduped. */
  completedDates: string[];
  /** ISO YYYY-MM-DD strings the app saw a 404 for. Sorted ascending, deduped. */
  knownOffDays: string[];
}

export interface Storage {
  /** Per-league completion + off-day records. */
  leagues: Record<League, LeagueState>;
  /** Sticky preference: the league this user most recently *played*. */
  lastPlayedLeague: League | null;
  settings: Settings;
  /** Bump if the shape changes. */
  schemaVersion: typeof SCHEMA_VERSION;
}

/**
 * Minimal contract we need from a localStorage-like backend. Matches the
 * subset of the DOM `Storage` interface we actually use, so a real
 * `window.localStorage` satisfies it without any adapter.
 */
export interface StorageBackend {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

// ---------------------------------------------------------------------------
// Defaults + validation
// ---------------------------------------------------------------------------

function emptyLeagueState(): LeagueState {
  return { completedDates: [], knownOffDays: [] };
}

export function defaultState(): Storage {
  return {
    leagues: { nba: emptyLeagueState(), wnba: emptyLeagueState() },
    lastPlayedLeague: null,
    settings: {},
    schemaVersion: SCHEMA_VERSION,
  };
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isIsoDate(v: unknown): v is string {
  return typeof v === "string" && ISO_DATE.test(v);
}

function isStringArrayOfDates(v: unknown): v is string[] {
  return Array.isArray(v) && v.every(isIsoDate);
}

function isLeague(v: unknown): v is League {
  return v === "nba" || v === "wnba";
}

function normalizeLeagueState(raw: unknown): LeagueState {
  if (!raw || typeof raw !== "object") {
    return emptyLeagueState();
  }
  const obj = raw as Record<string, unknown>;
  const completed = isStringArrayOfDates(obj.completedDates)
    ? obj.completedDates
    : [];
  const offDays = isStringArrayOfDates(obj.knownOffDays)
    ? obj.knownOffDays
    : [];
  return {
    completedDates: sortedUnique(completed),
    knownOffDays: sortedUnique(offDays),
  };
}

/**
 * Best-effort validator + migrator for a deserialized payload.
 *
 * Recognizes both v1 (flat completedDates/knownOffDays at the root) and v2
 * (per-league `leagues.<league>` shape). On v1 → v2 migration, all legacy
 * dates land under `leagues.nba` because v1 had no concept of leagues.
 *
 * Returns a normalized v2 `Storage`; throws if the input is recognizably
 * neither shape.
 */
function validateAndNormalize(raw: unknown): Storage {
  if (!raw || typeof raw !== "object") {
    throw new Error("storage payload is not an object");
  }
  const obj = raw as Record<string, unknown>;

  // v1 → v2 migration path. Legacy users get their NBA history preserved;
  // their WNBA state starts empty.
  if (obj.schemaVersion === 1) {
    const completed = isStringArrayOfDates(obj.completedDates)
      ? obj.completedDates
      : [];
    const offDays = isStringArrayOfDates(obj.knownOffDays)
      ? obj.knownOffDays
      : [];
    const settings = pickSettings(obj.settings);
    return {
      leagues: {
        nba: {
          completedDates: sortedUnique(completed),
          knownOffDays: sortedUnique(offDays),
        },
        wnba: emptyLeagueState(),
      },
      lastPlayedLeague: completed.length > 0 ? "nba" : null,
      settings,
      schemaVersion: SCHEMA_VERSION,
    };
  }

  if (obj.schemaVersion !== SCHEMA_VERSION) {
    throw new Error(`unsupported schemaVersion: ${String(obj.schemaVersion)}`);
  }

  const leaguesRaw = obj.leagues as Record<string, unknown> | undefined;
  if (!leaguesRaw || typeof leaguesRaw !== "object") {
    throw new Error("leagues is missing or not an object");
  }

  const lastPlayed = isLeague(obj.lastPlayedLeague)
    ? obj.lastPlayedLeague
    : null;

  return {
    leagues: {
      nba: normalizeLeagueState(leaguesRaw.nba),
      wnba: normalizeLeagueState(leaguesRaw.wnba),
    },
    lastPlayedLeague: lastPlayed,
    settings: pickSettings(obj.settings),
    schemaVersion: SCHEMA_VERSION,
  };
}

function pickSettings(raw: unknown): Settings {
  if (!raw || typeof raw !== "object") return {};
  const settings = raw as Record<string, unknown>;
  const out: Settings = {};
  if (typeof settings.timerHidden === "boolean") {
    out.timerHidden = settings.timerHidden;
  }
  return out;
}

function sortedUnique(dates: string[]): string[] {
  return Array.from(new Set(dates)).sort();
}

// ---------------------------------------------------------------------------
// Backend resolution
// ---------------------------------------------------------------------------

function resolveBackend(): StorageBackend | null {
  try {
    const ls = (globalThis as { localStorage?: StorageBackend }).localStorage;
    if (!ls) return null;
    if (
      typeof ls.getItem !== "function" ||
      typeof ls.setItem !== "function" ||
      typeof ls.removeItem !== "function"
    ) {
      return null;
    }
    return ls;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Read / write
// ---------------------------------------------------------------------------

export function loadState(
  backend: StorageBackend | null = resolveBackend(),
): Storage {
  if (!backend) return defaultState();
  let raw: string | null;
  try {
    raw = backend.getItem(STORAGE_KEY);
  } catch {
    return defaultState();
  }
  if (raw === null) return defaultState();
  try {
    const parsed = JSON.parse(raw) as unknown;
    return validateAndNormalize(parsed);
  } catch (err) {
    if (typeof console !== "undefined" && console.warn) {
      console.warn(
        "[nba-mini] resetting localStorage — stored value was malformed:",
        err,
      );
    }
    try {
      backend.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    return defaultState();
  }
}

export function saveState(
  state: Storage,
  backend: StorageBackend | null = resolveBackend(),
): void {
  if (!backend) return;
  try {
    backend.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (err) {
    if (typeof console !== "undefined" && console.warn) {
      console.warn("[nba-mini] failed to persist localStorage:", err);
    }
  }
}

// ---------------------------------------------------------------------------
// Pure transitions
// ---------------------------------------------------------------------------

function withDate(list: string[], date: string): string[] {
  if (!isIsoDate(date)) {
    throw new Error(`invalid ISO date: ${date}`);
  }
  if (list.includes(date)) return list;
  return [...list, date].sort();
}

/** Pure: returns a new state with `date` added to a league's `completedDates`. */
export function addCompletion(
  state: Storage,
  league: League,
  date: string,
): Storage {
  const current = state.leagues[league];
  return {
    ...state,
    leagues: {
      ...state.leagues,
      [league]: {
        ...current,
        completedDates: withDate(current.completedDates, date),
      },
    },
    lastPlayedLeague: league,
  };
}

/** Pure: returns a new state with `date` added to a league's `knownOffDays`. */
export function addOffDay(
  state: Storage,
  league: League,
  date: string,
): Storage {
  const current = state.leagues[league];
  return {
    ...state,
    leagues: {
      ...state.leagues,
      [league]: {
        ...current,
        knownOffDays: withDate(current.knownOffDays, date),
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Read+mutate convenience
// ---------------------------------------------------------------------------

export function recordCompletion(
  league: League,
  date: string,
  backend: StorageBackend | null = resolveBackend(),
): Storage {
  const next = addCompletion(loadState(backend), league, date);
  saveState(next, backend);
  return next;
}

export function markOffDay(
  league: League,
  date: string,
  backend: StorageBackend | null = resolveBackend(),
): Storage {
  const next = addOffDay(loadState(backend), league, date);
  saveState(next, backend);
  return next;
}

/** Read the user's sticky last-played league preference. */
export function getLastPlayedLeague(
  backend: StorageBackend | null = resolveBackend(),
): League | null {
  return loadState(backend).lastPlayedLeague;
}

export function settings(
  backend: StorageBackend | null = resolveBackend(),
): Settings {
  return loadState(backend).settings;
}

export function updateSettings(
  patch: Partial<Settings>,
  backend: StorageBackend | null = resolveBackend(),
): Storage {
  const current = loadState(backend);
  const next: Storage = {
    ...current,
    settings: { ...current.settings, ...patch },
  };
  saveState(next, backend);
  return next;
}

// ---------------------------------------------------------------------------
// Streak computation
// ---------------------------------------------------------------------------

export function previousDate(date: string): string {
  if (!isIsoDate(date)) {
    throw new Error(`invalid ISO date: ${date}`);
  }
  const [y, m, d] = date.split("-").map((s) => parseInt(s, 10));
  const t = Date.UTC(y, m - 1, d);
  const prev = new Date(t - 24 * 60 * 60 * 1000);
  const yy = prev.getUTCFullYear();
  const mm = String(prev.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(prev.getUTCDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

/**
 * Compute the current streak for `league` ending at `today`.
 *
 * Algorithm walks backwards from today: completed days extend the streak,
 * known off-days skip without breaking, anything else (unknown day or
 * missed-puzzle day) terminates. Capped at 10k steps as paranoia against
 * pathological inputs.
 */
export function computeStreak(
  state: Storage,
  league: League,
  today: string,
): number {
  if (!isIsoDate(today)) {
    throw new Error(`invalid ISO date: ${today}`);
  }
  const ls = state.leagues[league];
  const completed = new Set(ls.completedDates);
  const offDays = new Set(ls.knownOffDays);
  let cursor = today;
  let count = 0;
  for (let i = 0; i < 10_000; i++) {
    if (completed.has(cursor)) {
      count += 1;
      cursor = previousDate(cursor);
      continue;
    }
    if (offDays.has(cursor)) {
      cursor = previousDate(cursor);
      continue;
    }
    break;
  }
  return count;
}

export function getStreak(
  league: League,
  today: string,
  backend: StorageBackend | null = resolveBackend(),
): number {
  return computeStreak(loadState(backend), league, today);
}

/**
 * Streak to show for display *before* the user has completed today's puzzle.
 * Starts the cursor at yesterday so a returning user with a 5-day streak
 * sees "🔥 5" on load instead of "0".
 */
export function getDisplayStreak(
  league: League,
  today: string,
  backend: StorageBackend | null = resolveBackend(),
): number {
  const state = loadState(backend);
  if (state.leagues[league].completedDates.includes(today)) {
    return computeStreak(state, league, today);
  }
  return computeStreak(state, league, previousDate(today));
}
