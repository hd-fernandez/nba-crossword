"use client";

import type { Puzzle } from "@/lib/puzzle";
import { formatElapsed } from "@/lib/share";
import { Share } from "./Share";

interface FinishScreenProps {
  puzzle: Puzzle;
  elapsedMs: number;
  revealed: boolean[][];
  /**
   * Streak count to display. v0 hardcodes 1 from the page; U12 wires the
   * real localStorage-backed value.
   */
  streak: number;
}

/**
 * Modal overlay rendered when the puzzle is complete.
 *
 * v0 confetti = a static 🎉 emoji. U13 polish can replace with a real
 * animation; pulling in a confetti library would bloat the bundle for
 * something that ships behind a one-time gate.
 *
 * No "play again" button — today's puzzle is today's puzzle. v0 design.
 */
export function FinishScreen({
  puzzle,
  elapsedMs,
  revealed,
  streak,
}: FinishScreenProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="finish-title"
      data-testid="finish-screen"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(20, 20, 20, 0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        zIndex: 50,
      }}
    >
      <div
        style={{
          background: "#fffdf6",
          borderRadius: 12,
          maxWidth: 360,
          width: "100%",
          padding: "28px 24px",
          boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
          textAlign: "center",
          fontFamily: "inherit",
        }}
      >
        <div
          aria-hidden
          data-testid="finish-confetti"
          style={{ fontSize: 44, lineHeight: 1, marginBottom: 8 }}
        >
          🎉
        </div>
        <h2
          id="finish-title"
          style={{
            fontFamily: '"Iowan Old Style", "Charter", "Georgia", serif',
            fontSize: 24,
            margin: "0 0 16px",
          }}
        >
          Solved!
        </h2>

        <dl
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 6,
            margin: "0 0 20px",
            textAlign: "center",
          }}
        >
          <div>
            <dt style={statLabel}>Time</dt>
            <dd
              data-testid="finish-time"
              style={{ ...statValue, fontVariantNumeric: "tabular-nums" }}
            >
              {formatElapsed(elapsedMs)}
            </dd>
          </div>
          <div>
            <dt style={statLabel}>Streak</dt>
            <dd data-testid="finish-streak" style={statValue}>
              {streak}
            </dd>
          </div>
        </dl>

        <Share puzzle={puzzle} elapsedMs={elapsedMs} revealed={revealed} />
      </div>
    </div>
  );
}

const statLabel: React.CSSProperties = {
  fontSize: 11,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "#888",
  margin: 0,
};

const statValue: React.CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  margin: "2px 0 0",
  color: "#1a1a1a",
};
