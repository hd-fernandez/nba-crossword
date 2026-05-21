import { afterEach, describe, expect, it, vi } from "vitest";

import {
  STORAGE_KEY,
  SCHEMA_VERSION,
  addCompletion,
  addOffDay,
  computeStreak,
  defaultState,
  getDisplayStreak,
  getLastPlayedLeague,
  getStreak,
  loadState,
  markOffDay,
  previousDate,
  recordCompletion,
  saveState,
  settings,
  type Storage,
  type StorageBackend,
  updateSettings,
} from "@/lib/storage";

// ---------------------------------------------------------------------------
// In-memory backend for tests.
// ---------------------------------------------------------------------------

function makeBackend(initial: Record<string, string> = {}): StorageBackend & {
  data: Record<string, string>;
} {
  const data: Record<string, string> = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => {
      data[k] = v;
    },
    removeItem: (k) => {
      delete data[k];
    },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Defaults + load/save
// ---------------------------------------------------------------------------

describe("defaultState", () => {
  it("returns an empty per-league shape with the current schemaVersion", () => {
    const s = defaultState();
    expect(s.schemaVersion).toBe(SCHEMA_VERSION);
    expect(s.leagues.nba).toEqual({ completedDates: [], knownOffDays: [] });
    expect(s.leagues.wnba).toEqual({ completedDates: [], knownOffDays: [] });
    expect(s.lastPlayedLeague).toBeNull();
  });
});

describe("loadState", () => {
  it("returns defaults when the backend is unavailable", () => {
    expect(loadState(null)).toEqual(defaultState());
  });

  it("returns defaults when the key is missing", () => {
    const backend = makeBackend();
    expect(loadState(backend)).toEqual(defaultState());
  });

  it("round-trips a v2 payload through save+load", () => {
    const backend = makeBackend();
    const state = addCompletion(defaultState(), "nba", "2026-05-21");
    saveState(state, backend);
    expect(loadState(backend)).toEqual(state);
  });

  it("resets and warns when the stored JSON is malformed", () => {
    const backend = makeBackend({ [STORAGE_KEY]: "{not json" });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const result = loadState(backend);
    expect(result).toEqual(defaultState());
    expect(backend.data[STORAGE_KEY]).toBeUndefined();
    expect(warn).toHaveBeenCalled();
  });

  it("resets when the payload has the wrong shape", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({ schemaVersion: 99 }),
    });
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(loadState(backend)).toEqual(defaultState());
  });

  it("normalizes a payload by sorting + deduping date arrays", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({
        schemaVersion: SCHEMA_VERSION,
        leagues: {
          nba: {
            completedDates: ["2026-05-21", "2026-05-19", "2026-05-21"],
            knownOffDays: [],
          },
          wnba: { completedDates: [], knownOffDays: [] },
        },
        lastPlayedLeague: "nba",
        settings: {},
      }),
    });
    const result = loadState(backend);
    expect(result.leagues.nba.completedDates).toEqual([
      "2026-05-19",
      "2026-05-21",
    ]);
  });

  it("ignores unknown settings fields", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({
        schemaVersion: SCHEMA_VERSION,
        leagues: {
          nba: { completedDates: [], knownOffDays: [] },
          wnba: { completedDates: [], knownOffDays: [] },
        },
        lastPlayedLeague: null,
        settings: { timerHidden: true, garbage: 42 },
      }),
    });
    const result = loadState(backend);
    expect(result.settings).toEqual({ timerHidden: true });
  });

  it("survives a backend that throws on getItem", () => {
    const backend: StorageBackend = {
      getItem: () => {
        throw new Error("boom");
      },
      setItem: () => {},
      removeItem: () => {},
    };
    expect(loadState(backend)).toEqual(defaultState());
  });
});

describe("saveState", () => {
  it("is a silent no-op when backend is null", () => {
    expect(() => saveState(defaultState(), null)).not.toThrow();
  });

  it("warns but doesn't throw when setItem fails", () => {
    const backend: StorageBackend = {
      getItem: () => null,
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => {},
    };
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(() => saveState(defaultState(), backend)).not.toThrow();
    expect(warn).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// v1 → v2 migration
// ---------------------------------------------------------------------------

describe("v1 → v2 migration", () => {
  it("migrates a v1 payload's flat dates into leagues.nba", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({
        schemaVersion: 1,
        completedDates: ["2026-05-19", "2026-05-21"],
        knownOffDays: ["2026-05-20"],
        settings: { timerHidden: true },
      }),
    });
    const result = loadState(backend);
    expect(result.schemaVersion).toBe(SCHEMA_VERSION);
    expect(result.leagues.nba.completedDates).toEqual([
      "2026-05-19",
      "2026-05-21",
    ]);
    expect(result.leagues.nba.knownOffDays).toEqual(["2026-05-20"]);
    expect(result.leagues.wnba).toEqual({
      completedDates: [],
      knownOffDays: [],
    });
    expect(result.lastPlayedLeague).toBe("nba");
    expect(result.settings).toEqual({ timerHidden: true });
  });

  it("v1 with no completions leaves lastPlayedLeague null", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({
        schemaVersion: 1,
        completedDates: [],
        knownOffDays: [],
        settings: {},
      }),
    });
    expect(loadState(backend).lastPlayedLeague).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// previousDate
// ---------------------------------------------------------------------------

describe("previousDate", () => {
  it("steps back one day", () => {
    expect(previousDate("2026-05-21")).toBe("2026-05-20");
  });
  it("crosses month boundary", () => {
    expect(previousDate("2026-06-01")).toBe("2026-05-31");
  });
  it("crosses year boundary", () => {
    expect(previousDate("2026-01-01")).toBe("2025-12-31");
  });
  it("handles a leap-year boundary", () => {
    expect(previousDate("2024-03-01")).toBe("2024-02-29");
  });
  it("rejects a non-ISO input", () => {
    expect(() => previousDate("not-a-date")).toThrow();
  });
});

// ---------------------------------------------------------------------------
// addCompletion / addOffDay (pure)
// ---------------------------------------------------------------------------

describe("addCompletion + addOffDay", () => {
  it("addCompletion is idempotent and sorted", () => {
    let s: Storage = defaultState();
    s = addCompletion(s, "nba", "2026-05-21");
    s = addCompletion(s, "nba", "2026-05-19");
    s = addCompletion(s, "nba", "2026-05-21");
    expect(s.leagues.nba.completedDates).toEqual(["2026-05-19", "2026-05-21"]);
  });

  it("addCompletion sets lastPlayedLeague", () => {
    const s = addCompletion(defaultState(), "wnba", "2026-05-21");
    expect(s.lastPlayedLeague).toBe("wnba");
  });

  it("addOffDay does NOT set lastPlayedLeague", () => {
    const s = addOffDay(defaultState(), "wnba", "2026-05-20");
    expect(s.lastPlayedLeague).toBeNull();
  });

  it("rejects non-ISO date inputs", () => {
    expect(() => addCompletion(defaultState(), "nba", "garbage")).toThrow();
  });

  it("each league's state is independent", () => {
    let s: Storage = defaultState();
    s = addCompletion(s, "nba", "2026-05-21");
    expect(s.leagues.nba.completedDates).toEqual(["2026-05-21"]);
    expect(s.leagues.wnba.completedDates).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// computeStreak
// ---------------------------------------------------------------------------

describe("computeStreak", () => {
  it("0 on empty state", () => {
    expect(computeStreak(defaultState(), "nba", "2026-05-21")).toBe(0);
  });

  it("1 after a single completion of today", () => {
    const s = addCompletion(defaultState(), "nba", "2026-05-21");
    expect(computeStreak(s, "nba", "2026-05-21")).toBe(1);
  });

  it("counts consecutive completions", () => {
    let s: Storage = defaultState();
    for (const d of ["2026-05-19", "2026-05-20", "2026-05-21"]) {
      s = addCompletion(s, "nba", d);
    }
    expect(computeStreak(s, "nba", "2026-05-21")).toBe(3);
  });

  it("intervening off-day does not break the streak", () => {
    let s: Storage = defaultState();
    s = addCompletion(s, "nba", "2026-05-19");
    s = addOffDay(s, "nba", "2026-05-20");
    s = addCompletion(s, "nba", "2026-05-21");
    expect(computeStreak(s, "nba", "2026-05-21")).toBe(2);
  });

  it("missed-puzzle day breaks the streak", () => {
    let s: Storage = defaultState();
    s = addCompletion(s, "nba", "2026-05-19");
    s = addCompletion(s, "nba", "2026-05-21");
    expect(computeStreak(s, "nba", "2026-05-21")).toBe(1);
  });

  it("multi-off-day skip preserves the streak", () => {
    let s: Storage = defaultState();
    s = addCompletion(s, "nba", "2026-05-18");
    s = addOffDay(s, "nba", "2026-05-19");
    s = addOffDay(s, "nba", "2026-05-20");
    s = addCompletion(s, "nba", "2026-05-21");
    expect(computeStreak(s, "nba", "2026-05-21")).toBe(2);
  });

  it("each league's streak is independent", () => {
    let s: Storage = defaultState();
    s = addCompletion(s, "nba", "2026-05-21");
    s = addCompletion(s, "wnba", "2026-05-19");
    expect(computeStreak(s, "nba", "2026-05-21")).toBe(1);
    expect(computeStreak(s, "wnba", "2026-05-21")).toBe(0);
    expect(computeStreak(s, "wnba", "2026-05-19")).toBe(1);
  });

  it("rejects a non-ISO `today`", () => {
    expect(() => computeStreak(defaultState(), "nba", "bad")).toThrow();
  });
});

// ---------------------------------------------------------------------------
// recordCompletion + markOffDay
// ---------------------------------------------------------------------------

describe("recordCompletion + markOffDay", () => {
  it("recordCompletion persists and is idempotent", () => {
    const backend = makeBackend();
    recordCompletion("nba", "2026-05-21", backend);
    recordCompletion("nba", "2026-05-21", backend);
    expect(loadState(backend).leagues.nba.completedDates).toEqual([
      "2026-05-21",
    ]);
  });

  it("recordCompletion updates lastPlayedLeague", () => {
    const backend = makeBackend();
    recordCompletion("wnba", "2026-05-21", backend);
    expect(getLastPlayedLeague(backend)).toBe("wnba");
  });

  it("markOffDay persists and is idempotent", () => {
    const backend = makeBackend();
    markOffDay("nba", "2026-05-20", backend);
    markOffDay("nba", "2026-05-20", backend);
    expect(loadState(backend).leagues.nba.knownOffDays).toEqual([
      "2026-05-20",
    ]);
  });

  it("recording completion takes priority over off-day for streak math", () => {
    const backend = makeBackend();
    markOffDay("nba", "2026-05-21", backend);
    recordCompletion("nba", "2026-05-21", backend);
    expect(getStreak("nba", "2026-05-21", backend)).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// settings + updateSettings
// ---------------------------------------------------------------------------

describe("settings + updateSettings", () => {
  it("default settings are empty", () => {
    expect(settings(makeBackend())).toEqual({});
  });

  it("updateSettings merges without clobbering", () => {
    const backend = makeBackend();
    updateSettings({ timerHidden: true }, backend);
    expect(settings(backend)).toEqual({ timerHidden: true });
    updateSettings({}, backend);
    expect(settings(backend)).toEqual({ timerHidden: true });
  });

  it("updateSettings overwrites a value when explicitly given", () => {
    const backend = makeBackend();
    updateSettings({ timerHidden: true }, backend);
    updateSettings({ timerHidden: false }, backend);
    expect(settings(backend)).toEqual({ timerHidden: false });
  });
});

// ---------------------------------------------------------------------------
// getStreak / getDisplayStreak
// ---------------------------------------------------------------------------

describe("getStreak", () => {
  it("0 on empty state", () => {
    expect(getStreak("nba", "2026-05-21", makeBackend())).toBe(0);
  });

  it("returns the streak after a recorded completion", () => {
    const backend = makeBackend();
    recordCompletion("nba", "2026-05-21", backend);
    expect(getStreak("nba", "2026-05-21", backend)).toBe(1);
  });
});

describe("getDisplayStreak", () => {
  it("starts the cursor at yesterday so an existing run shows up on load", () => {
    const backend = makeBackend();
    for (const d of [
      "2026-05-16",
      "2026-05-17",
      "2026-05-18",
      "2026-05-19",
      "2026-05-20",
    ]) {
      recordCompletion("nba", d, backend);
    }
    expect(getDisplayStreak("nba", "2026-05-21", backend)).toBe(5);
  });

  it("once today is recorded, includes today in the count", () => {
    const backend = makeBackend();
    recordCompletion("nba", "2026-05-20", backend);
    recordCompletion("nba", "2026-05-21", backend);
    expect(getDisplayStreak("nba", "2026-05-21", backend)).toBe(2);
  });

  it("0 when there's no recent run", () => {
    expect(getDisplayStreak("nba", "2026-05-21", makeBackend())).toBe(0);
  });

  it("respects off-days when stepping back from yesterday", () => {
    const backend = makeBackend();
    recordCompletion("nba", "2026-05-19", backend);
    markOffDay("nba", "2026-05-20", backend);
    expect(getDisplayStreak("nba", "2026-05-21", backend)).toBe(1);
  });
});
