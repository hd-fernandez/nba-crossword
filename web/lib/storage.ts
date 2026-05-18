/**
 * localStorage-backed user state for the NBA Mini.
 *
 * Single key (`STORAGE_KEY`), JSON-serialized. We deliberately keep the shape
 * tiny and version-tagged so that a future schema change can either migrate
 * forward or reset cleanly.
 *
 * Streak rule (per the v0 plan, U12):
 *   - completion = streak day
 *   - off-days (no puzzle existed) skip; they neither break nor extend
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

export const STORAGE_KEY = "nba-mini-state";
export const SCHEMA_VERSION = 1 as const;

export interface Settings {
  /** Future-proofing for U13's persistent "hide timer" toggle. */
  timerHidden?: boolean;
}

export interface Storage {
  /** ISO YYYY-MM-DD strings, sorted ascending, deduped. */
  completedDates: string[];
  /** ISO YYYY-MM-DD strings the app saw a 404 for. Sorted ascending, deduped. */
  knownOffDays: string[];
  settings: Settings;
  /** Bump if the shape changes; v0 only handles v1. */
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

export function defaultState(): Storage {
  return {
    completedDates: [],
    knownOffDays: [],
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

/**
 * Best-effort validator for a deserialized payload. Returns a normalized
 * `Storage` if the shape is recognizable; throws otherwise. We sort + dedupe
 * the date arrays so downstream computation can rely on canonical form.
 */
function validateAndNormalize(raw: unknown): Storage {
  if (!raw || typeof raw !== "object") {
    throw new Error("storage payload is not an object");
  }
  const obj = raw as Record<string, unknown>;
  if (obj.schemaVersion !== SCHEMA_VERSION) {
    throw new Error(`unsupported schemaVersion: ${String(obj.schemaVersion)}`);
  }
  if (!isStringArrayOfDates(obj.completedDates)) {
    throw new Error("completedDates is not an array of ISO dates");
  }
  if (!isStringArrayOfDates(obj.knownOffDays)) {
    throw new Error("knownOffDays is not an array of ISO dates");
  }
  if (!obj.settings || typeof obj.settings !== "object") {
    throw new Error("settings is missing or not an object");
  }
  const settings = obj.settings as Record<string, unknown>;
  const cleanSettings: Settings = {};
  if (typeof settings.timerHidden === "boolean") {
    cleanSettings.timerHidden = settings.timerHidden;
  }
  return {
    completedDates: sortedUnique(obj.completedDates),
    knownOffDays: sortedUnique(obj.knownOffDays),
    settings: cleanSettings,
    schemaVersion: SCHEMA_VERSION,
  };
}

function sortedUnique(dates: string[]): string[] {
  return Array.from(new Set(dates)).sort();
}

// ---------------------------------------------------------------------------
// Backend resolution
// ---------------------------------------------------------------------------

/**
 * Resolve the localStorage-like backend at call time. Returns `null` if
 * unavailable (SSR, private-mode quotas, or browsers that throw on access
 * to `globalThis.localStorage`). Wrapping in try/catch is paranoid but cheap.
 */
function resolveBackend(): StorageBackend | null {
  try {
    const ls = (globalThis as { localStorage?: StorageBackend }).localStorage;
    if (!ls) return null;
    // Touch it once — Safari private mode throws on `setItem`, not on read,
    // but a missing API surface should fail here.
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

/**
 * Read state from the backend. Always returns *some* `Storage`:
 *   - missing key → fresh defaults
 *   - malformed JSON or invalid shape → fresh defaults (and a console warning)
 *   - backend unavailable → fresh defaults
 *
 * Never throws.
 */
export function loadState(backend: StorageBackend | null = resolveBackend()): Storage {
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
    // Don't crash on tampered data; reset gracefully and warn so the user
    // (or a future debugger) sees that a wipe happened.
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

/**
 * Persist state to the backend. Silently no-ops if the backend is missing
 * or rejects the write (quota exceeded, private mode, etc.). This is fine
 * for v0 — losing an offline streak update is worse than crashing only on
 * machines that already can't persist.
 */
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

/** Pure: returns a new state with `date` added to `completedDates`. */
export function addCompletion(state: Storage, date: string): Storage {
  return { ...state, completedDates: withDate(state.completedDates, date) };
}

/** Pure: returns a new state with `date` added to `knownOffDays`. */
export function addOffDay(state: Storage, date: string): Storage {
  return { ...state, knownOffDays: withDate(state.knownOffDays, date) };
}

// ---------------------------------------------------------------------------
// Read+mutate convenience
// ---------------------------------------------------------------------------

/**
 * Idempotently record that the user completed the puzzle on `date`. Reads
 * the current persisted state, adds the date (deduped + sorted), persists,
 * and returns the new state.
 */
export function recordCompletion(
  date: string,
  backend: StorageBackend | null = resolveBackend(),
): Storage {
  const next = addCompletion(loadState(backend), date);
  saveState(next, backend);
  return next;
}

/**
 * Idempotently record that `date` was an off-day (no puzzle existed). Called
 * by the page when `fetchTodayPuzzle()` returns null so streaks don't break
 * on dormant nights.
 */
export function markOffDay(
  date: string,
  backend: StorageBackend | null = resolveBackend(),
): Storage {
  const next = addOffDay(loadState(backend), date);
  saveState(next, backend);
  return next;
}

/** Read settings from persisted state. */
export function settings(
  backend: StorageBackend | null = resolveBackend(),
): Settings {
  return loadState(backend).settings;
}

/** Merge a settings patch into persisted state. */
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

/**
 * Step `date` (ISO YYYY-MM-DD) backward by one day, returning the previous
 * ISO date. Pure UTC arithmetic — no timezone-dependent shifts.
 */
export function previousDate(date: string): string {
  if (!isIsoDate(date)) {
    throw new Error(`invalid ISO date: ${date}`);
  }
  const [y, m, d] = date.split("-").map((s) => parseInt(s, 10));
  // Construct a UTC date so day arithmetic doesn't get pulled into the local
  // timezone. We treat ISO strings as opaque calendar dates.
  const t = Date.UTC(y, m - 1, d);
  const prev = new Date(t - 24 * 60 * 60 * 1000);
  const yy = prev.getUTCFullYear();
  const mm = String(prev.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(prev.getUTCDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

/**
 * Compute the current streak ending at `today`.
 *
 * Algorithm:
 *   cursor ← today
 *   while true:
 *     if cursor in completedDates: count++; cursor−=1d
 *     elif cursor in knownOffDays: cursor−=1d  (skip, don't break)
 *     else: break  (unknown day or missed-puzzle day → streak ends)
 *   return count
 *
 * To guard against pathological inputs (e.g., an enormous knownOffDays list
 * with no completions), we cap the walk at 10,000 iterations. v0 will never
 * hit that — a year is 365 — but it's cheap insurance.
 */
export function computeStreak(state: Storage, today: string): number {
  if (!isIsoDate(today)) {
    throw new Error(`invalid ISO date: ${today}`);
  }
  const completed = new Set(state.completedDates);
  const offDays = new Set(state.knownOffDays);
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

/**
 * Convenience: read state and compute the streak ending at `today`. After
 * the user completes today's puzzle, callers should `recordCompletion(today)`
 * first (so today is in `completedDates`) and then call this.
 */
export function getStreak(
  today: string,
  backend: StorageBackend | null = resolveBackend(),
): number {
  return computeStreak(loadState(backend), today);
}

/**
 * Streak to show for display *before* the user has completed today's puzzle.
 *
 * Today's status is undecided — not yet in `completedDates`, possibly not yet
 * in `knownOffDays` — so starting the cursor at `today` would always trip
 * over an unknown day and report 0. We instead start at *yesterday* so a
 * returning user with a five-day run sees "🔥 5" on load, not "0".
 *
 * Per the plan: "start the cursor at yesterday, not today, when computing
 * streak for display before completing today's puzzle."
 */
export function getDisplayStreak(
  today: string,
  backend: StorageBackend | null = resolveBackend(),
): number {
  const state = loadState(backend);
  // If the user has already completed today (e.g., they're revisiting after
  // solving), surface the post-completion streak — including today.
  if (state.completedDates.includes(today)) {
    return computeStreak(state, today);
  }
  return computeStreak(state, previousDate(today));
}
