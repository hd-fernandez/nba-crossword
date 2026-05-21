"use client";

import { useEffect, useState } from "react";

import { type SolveState, elapsedMs } from "@/lib/state";
import { formatElapsed } from "@/lib/share";

interface TimerProps {
  state: SolveState;
}

/**
 * Visible elapsed-time readout with a "hide" toggle.
 *
 * The reducer state owns the timer *anchor* (`startedAt`, `accumulatedMs`,
 * `finishedAt`). This component:
 *   - reads those three fields,
 *   - re-renders itself once a second via `setInterval`,
 *   - computes the displayed elapsed value from the anchor on each render.
 *
 * That keeps action churn out of the reducer (no per-second `tick`
 * dispatches) and keeps the elapsed value testable as a pure function of
 * (state, now).
 *
 * Hiding the timer is a *display-only* toggle — the underlying anchor keeps
 * advancing, so revealing it again shows the correct value.
 */
export function Timer({ state }: TimerProps) {
  const [, forceTick] = useState(0);
  const [hidden, setHidden] = useState(false);

  // Tick once a second while running. We don't tick after finish (frozen)
  // or before first input (no anchor yet).
  const isRunning = state.startedAt !== null && state.finishedAt === null;
  useEffect(() => {
    if (!isRunning) return;
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [isRunning]);

  const display = formatElapsed(elapsedMs(state, Date.now()));

  return (
    <div
      data-testid="timer"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        fontSize: 14,
      }}
    >
      <span
        data-testid="timer-value"
        aria-label={hidden ? "Timer hidden" : `Elapsed time ${display}`}
        style={{
          minWidth: 52,
          fontVariantNumeric: "tabular-nums",
          fontWeight: 600,
          fontSize: 16,
          color: hidden ? "transparent" : "#1a1a1a",
          // Keep the layout stable when hidden — hide via opacity-equivalent.
          background: hidden ? "#e8e6df" : "transparent",
          borderRadius: 6,
          padding: "3px 8px",
          userSelect: "none",
          letterSpacing: "0.02em",
        }}
      >
        {display}
      </span>
      <button
        type="button"
        data-testid="timer-toggle"
        onClick={() => setHidden((h) => !h)}
        aria-pressed={hidden}
        style={{
          fontFamily: "var(--font-sans), system-ui, sans-serif",
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "#777",
          background: "transparent",
          border: "1px solid #d6d3c8",
          borderRadius: 999,
          padding: "3px 9px",
          cursor: "pointer",
          transition: "background 120ms ease, color 120ms ease",
        }}
      >
        {hidden ? "Show" : "Hide"}
      </button>
    </div>
  );
}
