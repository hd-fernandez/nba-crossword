import { afterEach, describe, expect, it, vi } from "vitest";

import {
  STORAGE_KEY,
  addCompletion,
  addOffDay,
  computeStreak,
  defaultState,
  getDisplayStreak,
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
//
// Mirrors the subset of the DOM Storage interface we use. We do NOT touch
// `globalThis.localStorage` directly so tests stay deterministic across the
// happy-dom shared global.
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
// loadState / saveState — round trip + robustness
// ---------------------------------------------------------------------------

describe("loadState / saveState", () => {
  it("returns fresh defaults when nothing is stored", () => {
    const backend = makeBackend();
    expect(loadState(backend)).toEqual(defaultState());
  });

  it("returns fresh defaults when the backend is null (SSR / no localStorage)", () => {
    expect(loadState(null)).toEqual(defaultState());
  });

  it("does not throw when saving against a null backend (SSR safe)", () => {
    expect(() => saveState(defaultState(), null)).not.toThrow();
  });

  it("round-trips a populated state", () => {
    const backend = makeBackend();
    const state: Storage = {
      completedDates: ["2026-05-10", "2026-05-12"],
      knownOffDays: ["2026-05-11"],
      settings: { timerHidden: true },
      schemaVersion: 1,
    };
    saveState(state, backend);
    expect(loadState(backend)).toEqual(state);
  });

  it("resets gracefully when the stored value is unparseable JSON", () => {
    const backend = makeBackend({ [STORAGE_KEY]: "{not-json" });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const state = loadState(backend);
    expect(state).toEqual(defaultState());
    expect(warn).toHaveBeenCalled();
    // Tampered key should be cleared.
    expect(backend.getItem(STORAGE_KEY)).toBeNull();
  });

  it("resets gracefully when the stored value has the wrong shape", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({ completedDates: 5 }),
    });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const state = loadState(backend);
    expect(state).toEqual(defaultState());
    expect(warn).toHaveBeenCalled();
  });

  it("resets gracefully when an unknown schemaVersion is stored", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({
        completedDates: [],
        knownOffDays: [],
        settings: {},
        schemaVersion: 99,
      }),
    });
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(loadState(backend)).toEqual(defaultState());
  });

  it("normalizes (sorts + dedupes) date arrays on load", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({
        completedDates: ["2026-05-12", "2026-05-10", "2026-05-12"],
        knownOffDays: ["2026-05-11", "2026-05-09", "2026-05-11"],
        settings: {},
        schemaVersion: 1,
      }),
    });
    const state = loadState(backend);
    expect(state.completedDates).toEqual(["2026-05-10", "2026-05-12"]);
    expect(state.knownOffDays).toEqual(["2026-05-09", "2026-05-11"]);
  });

  it("rejects non-ISO date strings in the stored arrays", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({
        completedDates: ["yesterday"],
        knownOffDays: [],
        settings: {},
        schemaVersion: 1,
      }),
    });
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(loadState(backend)).toEqual(defaultState());
  });

  it("does not persist timerHidden when it isn't a boolean", () => {
    const backend = makeBackend({
      [STORAGE_KEY]: JSON.stringify({
        completedDates: [],
        knownOffDays: [],
        settings: { timerHidden: "yes" },
        schemaVersion: 1,
      }),
    });
    expect(loadState(backend).settings).toEqual({});
  });

  it("does not crash if the backend's getItem throws", () => {
    const backend: StorageBackend = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {},
      removeItem: () => {},
    };
    expect(() => loadState(backend)).not.toThrow();
    expect(loadState(backend)).toEqual(defaultState());
  });

  it("does not crash if the backend's setItem throws (quota / private mode)", () => {
    const backend: StorageBackend = {
      getItem: () => null,
      setItem: () => {
        throw new Error("quota exceeded");
      },
      removeItem: () => {},
    };
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(() => saveState(defaultState(), backend)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// previousDate — date arithmetic
// ---------------------------------------------------------------------------

describe("previousDate", () => {
  it("steps back one day in normal cases", () => {
    expect(previousDate("2026-05-15")).toBe("2026-05-14");
    expect(previousDate("2026-05-02")).toBe("2026-05-01");
  });

  it("handles month boundaries", () => {
    expect(previousDate("2026-05-01")).toBe("2026-04-30");
    expect(previousDate("2026-03-01")).toBe("2026-02-28");
  });

  it("handles year boundaries", () => {
    expect(previousDate("2026-01-01")).toBe("2025-12-31");
  });

  it("handles leap years", () => {
    expect(previousDate("2024-03-01")).toBe("2024-02-29");
    expect(previousDate("2025-03-01")).toBe("2025-02-28");
  });

  it("rejects malformed input", () => {
    expect(() => previousDate("not-a-date")).toThrow();
    expect(() => previousDate("2026/05/15")).toThrow();
  });
});

// ---------------------------------------------------------------------------
// addCompletion / addOffDay — pure transitions
// ---------------------------------------------------------------------------

describe("addCompletion / addOffDay", () => {
  it("addCompletion is idempotent for the same date", () => {
    let s = defaultState();
    s = addCompletion(s, "2026-05-15");
    s = addCompletion(s, "2026-05-15");
    expect(s.completedDates).toEqual(["2026-05-15"]);
  });

  it("addCompletion keeps the array sorted", () => {
    let s = defaultState();
    s = addCompletion(s, "2026-05-15");
    s = addCompletion(s, "2026-05-13");
    s = addCompletion(s, "2026-05-14");
    expect(s.completedDates).toEqual(["2026-05-13", "2026-05-14", "2026-05-15"]);
  });

  it("addOffDay is idempotent and sorted", () => {
    let s = defaultState();
    s = addOffDay(s, "2026-05-12");
    s = addOffDay(s, "2026-05-10");
    s = addOffDay(s, "2026-05-12");
    expect(s.knownOffDays).toEqual(["2026-05-10", "2026-05-12"]);
  });

  it("rejects non-ISO date strings", () => {
    expect(() => addCompletion(defaultState(), "tomorrow")).toThrow();
    expect(() => addOffDay(defaultState(), "2026/05/15")).toThrow();
  });
});

// ---------------------------------------------------------------------------
// computeStreak — the heart of U12
// ---------------------------------------------------------------------------

describe("computeStreak", () => {
  it("returns 0 for a brand-new state", () => {
    expect(computeStreak(defaultState(), "2026-05-15")).toBe(0);
  });

  it("returns 1 after completing today", () => {
    const s = addCompletion(defaultState(), "2026-05-15");
    expect(computeStreak(s, "2026-05-15")).toBe(1);
  });

  it("returns the run length for consecutive completions", () => {
    let s = defaultState();
    s = addCompletion(s, "2026-05-13");
    s = addCompletion(s, "2026-05-14");
    s = addCompletion(s, "2026-05-15");
    expect(computeStreak(s, "2026-05-15")).toBe(3);
  });

  it("does not break across an intervening off-day (Mon + Wed = 2)", () => {
    let s = defaultState();
    s = addCompletion(s, "2026-05-11"); // Mon
    s = addOffDay(s, "2026-05-12"); // Tue (no puzzle)
    s = addCompletion(s, "2026-05-13"); // Wed
    expect(computeStreak(s, "2026-05-13")).toBe(2);
  });

  it("breaks when a missed *puzzle* day sits between completions", () => {
    // Complete Monday; Tuesday and Wednesday have puzzles but are not
    // completed and not marked off-day. Opening Thursday.
    let s = defaultState();
    s = addCompletion(s, "2026-05-11"); // Mon
    // Tuesday + Wednesday are unknown → break
    expect(computeStreak(s, "2026-05-14")).toBe(0);
  });

  it("counts back through multiple off-days correctly", () => {
    let s = defaultState();
    s = addCompletion(s, "2026-05-10");
    s = addOffDay(s, "2026-05-11");
    s = addOffDay(s, "2026-05-12");
    s = addCompletion(s, "2026-05-13");
    expect(computeStreak(s, "2026-05-13")).toBe(2);
  });

  it("returns 0 when today and yesterday are both unknown", () => {
    // User opens after a long absence. Many days back has completions, but
    // an unknown day cuts the streak immediately.
    let s = defaultState();
    s = addCompletion(s, "2026-04-01");
    expect(computeStreak(s, "2026-05-15")).toBe(0);
  });

  it("computing streak BEFORE today's completion: the cursor should start at yesterday", () => {
    // Per the plan, when displaying the streak before today is completed,
    // the caller passes `previousDate(today)` so the cursor doesn't trip
    // over an unknown today. Verify that pattern works.
    let s = defaultState();
    s = addCompletion(s, "2026-05-13");
    s = addCompletion(s, "2026-05-14");
    // Today is 2026-05-15 and not yet completed.
    expect(computeStreak(s, previousDate("2026-05-15"))).toBe(2);
  });

  it("AFTER completing today: count starts at today and includes it", () => {
    let s = defaultState();
    s = addCompletion(s, "2026-05-13");
    s = addCompletion(s, "2026-05-14");
    s = addCompletion(s, "2026-05-15");
    expect(computeStreak(s, "2026-05-15")).toBe(3);
  });

  it("recordCompletion is idempotent — refreshing doesn't double-count", () => {
    const backend = makeBackend();
    recordCompletion("2026-05-15", backend);
    recordCompletion("2026-05-15", backend);
    expect(loadState(backend).completedDates).toEqual(["2026-05-15"]);
    expect(computeStreak(loadState(backend), "2026-05-15")).toBe(1);
  });

  it("rejects non-ISO `today`", () => {
    expect(() => computeStreak(defaultState(), "tomorrow")).toThrow();
  });
});

// ---------------------------------------------------------------------------
// recordCompletion / markOffDay — backend-bound idempotency
// ---------------------------------------------------------------------------

describe("recordCompletion / markOffDay", () => {
  it("recordCompletion persists and is idempotent", () => {
    const backend = makeBackend();
    const after1 = recordCompletion("2026-05-15", backend);
    expect(after1.completedDates).toEqual(["2026-05-15"]);
    const after2 = recordCompletion("2026-05-15", backend);
    expect(after2.completedDates).toEqual(["2026-05-15"]);
    expect(loadState(backend).completedDates).toEqual(["2026-05-15"]);
  });

  it("markOffDay persists and is idempotent", () => {
    const backend = makeBackend();
    markOffDay("2026-05-15", backend);
    markOffDay("2026-05-15", backend);
    expect(loadState(backend).knownOffDays).toEqual(["2026-05-15"]);
  });

  it("a date can be both completed and an off-day without crashing (priority: completed)", () => {
    // Defensive: not a real flow, but if some prior version flagged
    // off-day before completion, completion should still count.
    const backend = makeBackend();
    markOffDay("2026-05-15", backend);
    recordCompletion("2026-05-15", backend);
    expect(computeStreak(loadState(backend), "2026-05-15")).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// settings / updateSettings
// ---------------------------------------------------------------------------

describe("settings / updateSettings", () => {
  it("returns empty settings by default", () => {
    const backend = makeBackend();
    expect(settings(backend)).toEqual({});
  });

  it("merges patches without clobbering other state", () => {
    const backend = makeBackend();
    recordCompletion("2026-05-15", backend);
    updateSettings({ timerHidden: true }, backend);
    const state = loadState(backend);
    expect(state.settings.timerHidden).toBe(true);
    expect(state.completedDates).toEqual(["2026-05-15"]);
  });

  it("updateSettings overwrites a previous value", () => {
    const backend = makeBackend();
    updateSettings({ timerHidden: true }, backend);
    updateSettings({ timerHidden: false }, backend);
    expect(loadState(backend).settings.timerHidden).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// getStreak — the convenience reader the page uses
// ---------------------------------------------------------------------------

describe("getStreak", () => {
  it("reads from the backend and returns 0 on empty state", () => {
    const backend = makeBackend();
    expect(getStreak("2026-05-15", backend)).toBe(0);
  });

  it("reflects subsequent recordCompletion calls", () => {
    const backend = makeBackend();
    expect(getStreak("2026-05-15", backend)).toBe(0);
    recordCompletion("2026-05-15", backend);
    expect(getStreak("2026-05-15", backend)).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// getDisplayStreak — pre-completion badge UX
// ---------------------------------------------------------------------------

describe("getDisplayStreak", () => {
  it("returns the prior run before today is solved (cursor starts at yesterday)", () => {
    const backend = makeBackend();
    recordCompletion("2026-05-13", backend);
    recordCompletion("2026-05-14", backend);
    // today=2026-05-15 not yet completed; display should show 2.
    expect(getDisplayStreak("2026-05-15", backend)).toBe(2);
  });

  it("returns the post-completion streak when today is already in completedDates", () => {
    const backend = makeBackend();
    recordCompletion("2026-05-13", backend);
    recordCompletion("2026-05-14", backend);
    recordCompletion("2026-05-15", backend);
    expect(getDisplayStreak("2026-05-15", backend)).toBe(3);
  });

  it("returns 0 when there is no recent run", () => {
    const backend = makeBackend();
    recordCompletion("2026-04-01", backend);
    expect(getDisplayStreak("2026-05-15", backend)).toBe(0);
  });

  it("respects off-days when stepping back from yesterday", () => {
    const backend = makeBackend();
    recordCompletion("2026-05-12", backend);
    markOffDay("2026-05-13", backend);
    recordCompletion("2026-05-14", backend);
    // today=2026-05-15 not completed; cursor starts at yesterday=05-14
    // (completed) → 05-13 (off-day, skip) → 05-12 (completed) → 05-11 (unknown).
    expect(getDisplayStreak("2026-05-15", backend)).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Multi-day scenario from the plan
// ---------------------------------------------------------------------------

describe("scenario: long absence with mixed missed/off days", () => {
  it("a multi-day absence containing missed puzzle days reports streak = 0", () => {
    // Plan says: opening after a long absence with multiple missed days
    // correctly reports 0.
    const backend = makeBackend();
    // Solid run two weeks ago.
    recordCompletion("2026-05-01", backend);
    recordCompletion("2026-05-02", backend);
    recordCompletion("2026-05-03", backend);
    // Then user disappears. Mark a couple of off-days observed when
    // reopening, but plenty of unknown days remain in between.
    markOffDay("2026-05-04", backend);
    markOffDay("2026-05-13", backend);
    expect(getStreak("2026-05-15", backend)).toBe(0);
  });

  it("a multi-day absence that's *only* off-days does not break the streak", () => {
    const backend = makeBackend();
    recordCompletion("2026-05-01", backend);
    recordCompletion("2026-05-02", backend);
    // The user disappears. Every day in between gets marked off-day on
    // each reopen. (Realistically the page would do this on each visit;
    // we simulate the cumulative result.)
    for (
      let d = previousDate("2026-05-15");
      d !== "2026-05-02";
      d = previousDate(d)
    ) {
      markOffDay(d, backend);
    }
    // Today (2026-05-15) is also an off-day for this scenario.
    markOffDay("2026-05-15", backend);
    expect(getStreak("2026-05-15", backend)).toBe(2);
  });
});
