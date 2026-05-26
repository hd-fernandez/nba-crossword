"use client";

import { useEffect, useState } from "react";

import type { BeePuzzle } from "@/lib/bee";
import { buildBeeShareText, shareOrCopyBee } from "@/lib/bee-share";

interface BeeFinishModalProps {
  puzzle: BeePuzzle;
  score: number;
  foundCount: number;
  /** League accent color for primary button + center hex echo. */
  accent: string;
  /** Called when the user dismisses (X, Escape, or backdrop). */
  onClose: () => void;
}

/**
 * Celebration overlay shown when the user reaches GOAT (every name found).
 * Pattern matches the crossword's `<FinishScreen>`: backdrop click /
 * Escape / X-button all dismiss; a "Show GOAT summary" button on the
 * Bee page brings it back. Confetti is a static 🏆 emoji for v3.
 */
export function BeeFinishModal({
  puzzle,
  score,
  foundCount,
  accent,
  onClose,
}: BeeFinishModalProps) {
  const [shareStatus, setShareStatus] = useState<
    "idle" | "shared" | "copied" | "unsupported" | "error"
  >("idle");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleShare() {
    const text = buildBeeShareText({ puzzle, score, foundCount });
    try {
      const result = await shareOrCopyBee(text);
      setShareStatus(result);
    } catch {
      // User cancelled the native share sheet — silent, leave idle.
      setShareStatus("idle");
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="bee-finish-title"
      data-testid="bee-finish-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(20, 20, 20, 0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          position: "relative",
          background: "#fffdf6",
          borderRadius: 14,
          maxWidth: 360,
          width: "100%",
          padding: "28px 24px",
          boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
          textAlign: "center",
        }}
      >
        <button
          type="button"
          aria-label="Close"
          data-testid="bee-finish-close"
          onClick={onClose}
          style={{
            position: "absolute",
            top: 8,
            right: 8,
            border: "none",
            background: "transparent",
            fontSize: 22,
            lineHeight: 1,
            padding: "4px 8px",
            cursor: "pointer",
            color: "#888",
          }}
        >
          ×
        </button>

        <div
          aria-hidden
          style={{
            fontSize: 48,
            lineHeight: 1,
            marginBottom: 8,
          }}
        >
          👑
        </div>

        <h2
          id="bee-finish-title"
          style={{
            fontFamily: 'var(--font-serif), Georgia, serif',
            fontSize: 26,
            fontWeight: 600,
            margin: "0 0 4px",
            letterSpacing: "-0.01em",
          }}
        >
          GOAT
        </h2>
        <p
          style={{
            margin: "0 0 18px",
            fontSize: 13,
            color: "#888",
          }}
        >
          Every name found.
        </p>

        <dl
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 6,
            margin: "0 0 18px",
            textAlign: "center",
          }}
        >
          <div>
            <dt style={statLabel}>Score</dt>
            <dd
              data-testid="bee-finish-score"
              style={{ ...statValue, fontVariantNumeric: "tabular-nums" }}
            >
              {score}
            </dd>
          </div>
          <div>
            <dt style={statLabel}>Names</dt>
            <dd data-testid="bee-finish-names" style={statValue}>
              {foundCount} / {puzzle.valid_names.length}
            </dd>
          </div>
        </dl>

        <button
          type="button"
          data-testid="bee-finish-share"
          onClick={handleShare}
          style={{
            background: accent,
            color: "#fff",
            border: "none",
            borderRadius: 999,
            padding: "11px 28px",
            fontSize: 15,
            fontWeight: 600,
            cursor: "pointer",
            letterSpacing: "0.02em",
            boxShadow: `0 4px 14px ${accent}55`,
          }}
        >
          Share
        </button>

        {shareStatus === "copied" && (
          <p
            data-testid="bee-finish-share-confirm"
            style={{
              margin: "12px 0 0",
              fontSize: 12,
              color: "#2e7d32",
              fontWeight: 500,
            }}
          >
            Copied!
          </p>
        )}
        {shareStatus === "unsupported" && (
          <p
            style={{
              margin: "12px 0 0",
              fontSize: 12,
              color: "#a04040",
            }}
          >
            Sharing not supported in this browser.
          </p>
        )}
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
