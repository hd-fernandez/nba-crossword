"use client";

import { useEffect, useMemo, useReducer, useState } from "react";

import { BeeFinishModal } from "@/components/BeeFinishModal";
import { BeeHive } from "@/components/BeeHive";
import { LeagueToggle } from "@/components/LeagueToggle";
import { configFor } from "@/lib/league";
import {
  scoreName,
  tierForScore,
  type BeeLeague,
  type BeePuzzle,
  type TierKey,
} from "@/lib/bee";
import { fetchBee } from "@/lib/bee-fetch";
import {
  beeReducer,
  initialBeeState,
  isBeeSolved,
  scoreState,
  type BeeAction,
  type BeeState,
  type EntryFeedback,
} from "@/lib/bee-state";
import { todayInEastern } from "@/lib/puzzle";

type BeeFetchStatus =
  | { kind: "loading" }
  | { kind: "ready"; puzzle: BeePuzzle }
  | { kind: "no-bee" }
  | { kind: "error"; message: string };

interface BeePageProps {
  league: BeeLeague;
}

const TIER_LABELS: Record<TierKey, string> = {
  g_league_callup: "G League Call-Up",
  rookie: "Rookie",
  sophomore: "Sophomore",
  vet: "Vet",
  all_star: "All-Star",
  champion: "Champion",
  hall_of_famer: "Hall of Famer",
  goat: "GOAT",
};

/**
 * The shared per-league Bee page. NBA at /nba/bee, WNBA at /wnba/bee,
 * combined at /bee. All three flavors render this same component with a
 * different `league`.
 */
export function BeePage({ league }: BeePageProps) {
  // For the combined Bee, fall back to NBA's accent for now — we don't
  // have a third palette in `lib/league.ts` yet. The combined identity
  // (gold? a third color?) is a v3.5 polish question.
  const cfg = league === "combined" ? configFor("nba") : configFor(league);
  const accent = cfg.theme.accent;

  const [status, setStatus] = useState<BeeFetchStatus>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchBee(league)
      .then((puzzle) => {
        if (cancelled) return;
        setStatus(puzzle ? { kind: "ready", puzzle } : { kind: "no-bee" });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStatus({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [league]);

  return (
    <>
      <div
        aria-hidden
        style={{
          position: "fixed",
          inset: 0,
          backgroundImage: `url(${cfg.heroPhoto})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          zIndex: -2,
        }}
      />
      <div
        aria-hidden
        style={{
          position: "fixed",
          inset: 0,
          background: cfg.theme.overlayGradient,
          zIndex: -1,
        }}
      />
      <main
        style={{
          minHeight: "100vh",
          padding: "32px 16px 48px",
          color: "#f7f7f5",
          fontFamily:
            'var(--font-sans), ui-sans-serif, system-ui, sans-serif',
        }}
      >
        <div style={{ maxWidth: 540, margin: "0 auto" }}>
          <header style={{ marginBottom: 14 }}>
            <h1
              style={{
                fontFamily:
                  'var(--font-serif), "Iowan Old Style", Georgia, serif',
                fontSize: 36,
                fontWeight: 600,
                margin: "0 0 4px",
                letterSpacing: "-0.015em",
                color: "#fffdf6",
                textShadow: "0 1px 2px rgba(0,0,0,0.5)",
              }}
            >
              Hoops Bee
            </h1>
            <p
              style={{
                margin: 0,
                fontSize: 13,
                color: "rgba(255, 253, 246, 0.72)",
                letterSpacing: "0.01em",
                lineHeight: 1.45,
              }}
            >
              Form names of {league === "wnba" ? "WNBA" : league === "nba" ? "NBA" : "hoops"}
              {" "}players, coaches &amp; staff using the 7 letters. Every name must use the
              {" "}<strong style={{ color: accent }}>center letter</strong>. Min 4 letters; reuse letters anytime.
            </p>
          </header>

          <div
            style={{
              marginBottom: 18,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            {league !== "combined" && <LeagueToggle current={league} />}
            <a
              href={`/${league === "combined" ? "" : league}`}
              style={{
                fontSize: 12,
                color: "rgba(255,253,246,0.7)",
                textDecoration: "none",
                letterSpacing: "0.04em",
              }}
            >
              ← Back to crossword
            </a>
          </div>

          {status.kind === "loading" && (
            <div
              style={{
                background: "rgba(255,253,246,0.06)",
                border: "1px solid rgba(255,253,246,0.10)",
                borderRadius: 14,
                padding: "32px 20px",
                textAlign: "center",
                color: "rgba(247,247,245,0.55)",
                fontSize: 13,
                fontStyle: "italic",
              }}
            >
              Loading today&rsquo;s Bee&hellip;
            </div>
          )}

          {status.kind === "no-bee" && (
            <div
              role="status"
              data-testid="no-bee"
              style={{
                background: "rgba(255,253,246,0.96)",
                color: "#1a1a1a",
                borderRadius: 12,
                padding: 24,
                boxShadow: "0 12px 40px rgba(0,0,0,0.35)",
              }}
            >
              <h2 style={{ marginTop: 0 }}>No Bee today</h2>
              <p style={{ margin: 0 }}>Check back tomorrow.</p>
            </div>
          )}

          {status.kind === "error" && (
            <div
              role="alert"
              style={{
                color: "#fff",
                background: "rgba(160,0,0,0.85)",
                padding: 16,
                borderRadius: 8,
              }}
            >
              Couldn&rsquo;t load today&rsquo;s Bee: {status.message}
            </div>
          )}

          {status.kind === "ready" && (
            <BeeBoard puzzle={status.puzzle} accent={accent} />
          )}

          <footer
            style={{
              marginTop: 24,
              fontSize: 11,
              color: "rgba(247,247,245,0.55)",
              textAlign: "center",
              letterSpacing: "0.05em",
            }}
          >
            Photo: Unsplash · CC0
          </footer>
        </div>
      </main>
    </>
  );
}

function BeeBoard({ puzzle, accent }: { puzzle: BeePuzzle; accent: string }) {
  const reducer = useMemo(() => beeReducer(puzzle), [puzzle]);
  const [state, dispatch] = useReducer(reducer, initialBeeState());

  // Outer letters get a stable initial order, but the user can shuffle.
  // We track the order in a `useState` outside the reducer because shuffles
  // are a pure presentation concern and don't affect any derived state.
  const [outerOrder, setOuterOrder] = useState<string[]>(puzzle.outer_letters);
  const onShuffle = () => {
    const next = [...outerOrder];
    // Fisher-Yates one-pass.
    for (let i = next.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [next[i], next[j]] = [next[j], next[i]];
    }
    setOuterOrder(next);
    dispatch({ type: "shuffle" });
  };

  // Keyboard input. Listen on the page (not on a specific element) so the
  // user doesn't have to focus anything.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key;
      if (/^[a-zA-Z]$/.test(k)) {
        dispatch({ type: "type", letter: k });
        e.preventDefault();
      } else if (k === "Backspace") {
        dispatch({ type: "delete" });
        e.preventDefault();
      } else if (k === "Enter") {
        dispatch({ type: "submit" });
        e.preventDefault();
      } else if (k === "Escape") {
        dispatch({ type: "clearEntry" });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const score = scoreState(puzzle, state);
  const tier = tierForScore(score, puzzle.tier_thresholds, puzzle.max_score);
  const solved = isBeeSolved(puzzle, state);
  // GOAT modal can be dismissed; the solved state itself is permanent.
  // A "Show GOAT summary" button brings it back.
  const [finishDismissed, setFinishDismissed] = useState(false);

  return (
    <div
      style={{
        background: "rgba(255,253,246,0.97)",
        color: "#1a1a1a",
        borderRadius: 14,
        padding: 20,
        boxShadow: "0 16px 50px rgba(0,0,0,0.4)",
      }}
    >
      {/* Tier + score row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "#888",
              marginBottom: 2,
            }}
          >
            Tier
          </div>
          <div
            data-testid="bee-tier"
            style={{
              fontFamily: 'var(--font-serif), Georgia, serif',
              fontSize: 22,
              fontWeight: 600,
              color: tier ? "#1a1a1a" : "#aaa",
            }}
          >
            {tier ? TIER_LABELS[tier] : "Undrafted"}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "#888",
              marginBottom: 2,
            }}
          >
            Score
          </div>
          <div
            data-testid="bee-score"
            style={{
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: 20,
              fontWeight: 700,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {score} / {puzzle.max_score}
          </div>
        </div>
      </div>

      {/* Entry bar */}
      <EntryBar entry={state.entry} feedback={state.lastFeedback} feedbackKey={state.feedbackKey} />

      {/* Hexagon hive — pulses on a correct submission */}
      <div
        key={state.feedbackKey}
        data-testid="bee-hive-wrapper"
        data-correct={state.lastFeedback?.kind === "ok" ? "true" : "false"}
        style={{
          margin: "20px 0",
          animation:
            state.lastFeedback?.kind === "ok"
              ? "bee-correct-pulse 360ms ease-out"
              : undefined,
        }}
      >
        <BeeHive
          puzzle={puzzle}
          outerOrder={outerOrder}
          onTapLetter={(l) => dispatch({ type: "tap", letter: l })}
          accent={accent}
        />
      </div>
      {/* Keyframes for the animation. Inline so we don't need a global stylesheet. */}
      <style>{`
        @keyframes bee-correct-pulse {
          0%   { transform: scale(1); }
          40%  { transform: scale(1.05); }
          100% { transform: scale(1); }
        }
        @keyframes bee-feedback-rise {
          0%   { transform: translateY(0); opacity: 0; }
          15%  { transform: translateY(-8px); opacity: 1; }
          80%  { transform: translateY(-18px); opacity: 1; }
          100% { transform: translateY(-26px); opacity: 0; }
        }
      `}</style>

      {/* Action buttons */}
      <div
        style={{
          display: "flex",
          gap: 8,
          justifyContent: "center",
          marginBottom: 16,
        }}
      >
        <ActionButton onClick={() => dispatch({ type: "delete" })} label="Delete" />
        <ActionButton onClick={onShuffle} label="Shuffle" />
        <ActionButton
          onClick={() => dispatch({ type: "submit" })}
          label="Enter"
          accent={accent}
        />
      </div>

      {/* Found names list */}
      <FoundList
        found={state.found}
        valid={puzzle.valid_names}
        pangrams={puzzle.pangrams}
      />

      {/* Persistent share row — usable at any tier, not just GOAT. The
          share text reflects the user's current tier + score. */}
      <ShareRow
        puzzle={puzzle}
        score={score}
        foundCount={state.found.length}
        accent={accent}
      />

      {/* GOAT modal: pops once per session when the puzzle is solved.
          Dismissable via X / Escape / backdrop. A "Show GOAT summary"
          button reopens it. */}
      {solved && !finishDismissed && (
        <BeeFinishModal
          puzzle={puzzle}
          score={score}
          foundCount={state.found.length}
          accent={accent}
          onClose={() => setFinishDismissed(true)}
        />
      )}
      {solved && finishDismissed && (
        <button
          type="button"
          onClick={() => setFinishDismissed(false)}
          data-testid="bee-show-finish"
          style={{
            marginTop: 16,
            padding: "8px 14px",
            border: "1px solid #d6d3c8",
            borderRadius: 999,
            background: "#fff",
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 600,
            color: "#666",
          }}
        >
          Show GOAT summary
        </button>
      )}
    </div>
  );
}

function EntryBar({
  entry,
  feedback,
  feedbackKey,
}: {
  entry: string;
  feedback: EntryFeedback | null;
  feedbackKey: number;
}) {
  const placeholderShown = entry.length === 0;
  const message = feedback ? feedbackToMessage(feedback) : null;
  return (
    <div
      data-testid="bee-entry-bar"
      style={{
        position: "relative",
        textAlign: "center",
        minHeight: 44,
        padding: "10px 12px",
        fontFamily: "var(--font-sans), system-ui, sans-serif",
        fontSize: 22,
        fontWeight: 700,
        letterSpacing: "0.04em",
        color: placeholderShown ? "#bdbab2" : "#1a1a1a",
      }}
    >
      {placeholderShown ? "Type a name" : entry}
      {message && (
        <div
          key={feedbackKey}
          data-testid="bee-feedback"
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: "100%",
            marginTop: 4,
            fontSize: message.large ? 14 : 12,
            fontWeight: message.large ? 700 : 500,
            letterSpacing: "0.03em",
            color: message.color,
            animation: message.animate
              ? "bee-feedback-rise 1200ms ease-out forwards"
              : undefined,
          }}
        >
          {message.text}
        </div>
      )}
    </div>
  );
}

interface FeedbackMessage {
  text: string;
  color: string;
  animate: boolean;
  large: boolean;
}

function feedbackToMessage(f: EntryFeedback): FeedbackMessage {
  switch (f.kind) {
    case "ok":
      return {
        text: f.isPangram
          ? `Pangram! +${f.pointsGained} 🐝`
          : `+${f.pointsGained}`,
        color: f.isPangram ? "#c8102e" : "#2e7d32",
        animate: true,
        large: f.isPangram,
      };
    case "tooShort":
      return { text: "Too short", color: "#888", animate: false, large: false };
    case "missingCenter":
      return {
        text: "Must include the center letter",
        color: "#888",
        animate: false,
        large: false,
      };
    case "badLetters":
      return {
        text: "Letters not on the board",
        color: "#888",
        animate: false,
        large: false,
      };
    case "alreadyFound":
      return {
        text: "Already found",
        color: "#888",
        animate: false,
        large: false,
      };
    case "notInList":
      return {
        text: "Not in our list",
        color: "#a04040",
        animate: false,
        large: false,
      };
  }
}

function ActionButton({
  onClick,
  label,
  accent,
}: {
  onClick: () => void;
  label: string;
  accent?: string;
}) {
  const isPrimary = !!accent;
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`bee-action-${label.toLowerCase()}`}
      style={{
        padding: "10px 18px",
        borderRadius: 999,
        border: isPrimary ? "none" : "1px solid #d6d3c8",
        background: isPrimary ? accent : "#fff",
        color: isPrimary ? "#fff" : "#333",
        fontSize: 13,
        fontWeight: 600,
        letterSpacing: "0.05em",
        textTransform: "uppercase",
        cursor: "pointer",
        boxShadow: isPrimary ? `0 3px 10px ${accent}55` : "none",
      }}
    >
      {label}
    </button>
  );
}

function FoundList({
  found,
  valid,
  pangrams,
}: {
  found: string[];
  valid: string[];
  pangrams: string[];
}) {
  const [open, setOpen] = useState(false);
  const pangramSet = new Set(pangrams);
  return (
    <div data-testid="bee-found-list">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          padding: "8px 12px",
          background: "#f4f1ea",
          border: "1px solid #e0dccd",
          borderRadius: 8,
          fontSize: 13,
          textAlign: "left",
          cursor: "pointer",
          color: "#333",
          fontFamily: "var(--font-sans), system-ui, sans-serif",
        }}
      >
        Found {found.length} of {valid.length}{" "}
        <span style={{ color: "#999", fontWeight: 400 }}>
          ({open ? "hide" : "show"})
        </span>
      </button>
      {open && (
        <ul
          style={{
            margin: "8px 0 0",
            padding: "8px 12px",
            background: "#fffdf6",
            border: "1px solid #e8e6df",
            borderRadius: 8,
            listStyle: "none",
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            fontSize: 13,
          }}
        >
          {found.length === 0 && (
            <li style={{ color: "#999", fontStyle: "italic" }}>
              Names you find will appear here.
            </li>
          )}
          {found.map((name) => (
            <li
              key={name}
              style={{
                fontWeight: pangramSet.has(name) ? 700 : 500,
                color: pangramSet.has(name) ? "#7a4a00" : "#333",
              }}
            >
              {name}
              {pangramSet.has(name) && " 🐝"}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ShareRow({
  puzzle,
  score,
  foundCount,
  accent,
}: {
  puzzle: BeePuzzle;
  score: number;
  foundCount: number;
  accent: string;
}) {
  const [status, setStatus] = useState<
    "idle" | "shared" | "copied" | "unsupported" | "error"
  >("idle");

  async function onShare() {
    const { buildBeeShareText, shareOrCopyBee } = await import("@/lib/bee-share");
    const text = buildBeeShareText({ puzzle, score, foundCount });
    try {
      const result = await shareOrCopyBee(text);
      setStatus(result);
    } catch {
      setStatus("idle");
    }
  }

  // Don't show until the user has at least one find — share at zero is just confusing.
  if (foundCount === 0) return null;

  return (
    <div
      data-testid="bee-share-row"
      style={{
        marginTop: 16,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        padding: "10px 14px",
        background: "#f4f1ea",
        border: "1px solid #e0dccd",
        borderRadius: 8,
        fontSize: 13,
      }}
    >
      <span style={{ color: "#666" }}>
        Share your progress
      </span>
      <button
        type="button"
        onClick={onShare}
        data-testid="bee-share-button"
        style={{
          background: accent,
          color: "#fff",
          border: "none",
          borderRadius: 999,
          padding: "6px 16px",
          fontSize: 12,
          fontWeight: 600,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          cursor: "pointer",
        }}
      >
        {status === "copied" ? "Copied!" : "Share"}
      </button>
    </div>
  );
}
