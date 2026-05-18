"use client";

import { useState } from "react";

import type { Puzzle } from "@/lib/puzzle";
import { buildShareText, shareOrCopy } from "@/lib/share";

interface ShareProps {
  puzzle: Puzzle;
  elapsedMs: number;
  revealed: boolean[][];
}

/**
 * "Share" button that emits the pure-text grid via Web Share API or
 * clipboard fallback. Shows a brief "Copied!" confirmation on the
 * fallback path.
 *
 * The share text is computed lazily in the click handler so it always
 * reflects the latest props (relevant if a user reveals more cells while
 * the finish screen is open — though that's not a v0 flow).
 */
export function Share({ puzzle, elapsedMs, revealed }: ShareProps) {
  const [confirm, setConfirm] = useState<string | null>(null);

  async function onClick() {
    const text = buildShareText(puzzle, elapsedMs, revealed);
    try {
      const result = await shareOrCopy(text);
      if (result === "copied") {
        setConfirm("Copied!");
        // Brief confirmation; clears itself.
        setTimeout(() => setConfirm(null), 2000);
      } else {
        // Native share sheet handled its own UX; no inline confirmation.
        setConfirm(null);
      }
    } catch (err) {
      // AbortError = user cancelled the native sheet; everything else =
      // legit failure. Either way, surface a non-scary inline message.
      const name = (err as { name?: string })?.name;
      if (name !== "AbortError") {
        setConfirm("Couldn't share");
        setTimeout(() => setConfirm(null), 2000);
      }
    }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <button
        type="button"
        data-testid="share-button"
        onClick={onClick}
        style={{
          background: "#1a1a1a",
          color: "#fff",
          border: "none",
          borderRadius: 999,
          padding: "10px 22px",
          fontSize: 14,
          fontWeight: 600,
          cursor: "pointer",
          letterSpacing: "0.02em",
        }}
      >
        Share
      </button>
      {confirm && (
        <span
          data-testid="share-confirm"
          role="status"
          style={{ fontSize: 13, color: "#1a7f37" }}
        >
          {confirm}
        </span>
      )}
    </div>
  );
}
