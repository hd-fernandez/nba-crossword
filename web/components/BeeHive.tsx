"use client";

import { useMemo } from "react";

import type { BeePuzzle } from "@/lib/bee";

interface BeeHiveProps {
  puzzle: BeePuzzle;
  /** Display order of the 6 outer letters. Pass a freshly-shuffled copy
   *  to "shuffle" the board visually. */
  outerOrder: string[];
  /** Called when any board letter is clicked or tapped. */
  onTapLetter: (letter: string) => void;
  /** Accent color for the center cell. */
  accent: string;
}

/**
 * Six outer hexagons arranged in a flat-top honeycomb around a center
 * hexagon — same layout as NYT Spelling Bee.
 *
 * Hex math (pointy-top): for a hexagon with circumradius R,
 *   width  = sqrt(3) * R
 *   height = 2 * R
 *   neighbor offsets at 60° intervals: (sqrt(3)*R, 0), (sqrt(3)/2*R, 3/2*R), ...
 *
 * The viewBox is sized so the seven hexes fit with a small padding margin
 * — no cropping at top/bottom edges.
 */
export function BeeHive({ puzzle, outerOrder, onTapLetter, accent }: BeeHiveProps) {
  // Hex radius (circumradius) in SVG units. Bigger = bigger hexes.
  const R = 50;
  // Gap between adjacent hexes. Tiny so the honeycomb reads as a unit.
  const GAP = 3;

  // Pointy-top hexagon math:
  //   circumradius (vertex distance) = R
  //   inradius     (edge distance)   = R * sqrt(3)/2
  //   neighbor distance              = 2 * inradius + GAP = R * sqrt(3) + GAP
  // Six neighbors at 30°, 90°, 150°, 210°, 270°, 330° (top-right, top, top-left, ...)
  // For pointy-top hexagons the neighbor angles are at 0°/60°/120°/...
  // wait — pointy-top neighbors are at 30°, 90°, 150°, 210°, 270°, 330°.
  // Actually: pointy-top hexagons stack in column-aligned columns, and
  // their 6 nearest neighbors live at angles offset 30° from the vertices.
  // We'll place them at those angles.
  const neighborDistance = R * Math.sqrt(3) + GAP;

  const positions = useMemo(() => {
    // Six positions around the center, going clockwise from 12 o'clock.
    // Angles (measured from positive-x axis, clockwise from north):
    //   north(top)        = -90°
    //   north-east(2 o'c) = -30°
    //   south-east(4 o'c) =  30°
    //   south(bottom)     =  90°
    //   south-west(8 o'c) = 150°
    //   north-west(10 o'c)= 210° (or -150°)
    const angles = [-90, -30, 30, 90, 150, 210];
    return angles.map((deg) => {
      const rad = (deg * Math.PI) / 180;
      return {
        dx: neighborDistance * Math.cos(rad),
        dy: neighborDistance * Math.sin(rad),
      };
    });
  }, [neighborDistance]);

  // ViewBox sizing: the hive's full extent is (center hex) + (one hex
  // diameter beyond it on each side). Hex extent = R vertically (pointy
  // top, so vertex is straight up), R*sqrt(3)/2 horizontally (flat side).
  // The neighbors sit at distance `neighborDistance`, plus their own R
  // on top of that. We pad with a small margin so vertices don't touch.
  const PADDING = 12;
  const halfH = neighborDistance + R + PADDING; // vertical reach (top hex peak)
  const halfW = neighborDistance + R * (Math.sqrt(3) / 2) + PADDING; // horizontal
  const VIEW_W = halfW * 2;
  const VIEW_H = halfH * 2;

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      width="100%"
      style={{
        maxWidth: 360,
        display: "block",
        margin: "0 auto",
        userSelect: "none",
      }}
      data-testid="bee-hive"
    >
      {/* Outer hexes — drawn first so the center sits on top of any overlap. */}
      {positions.map((pos, i) => {
        const letter = outerOrder[i];
        if (!letter) return null;
        return (
          <Hex
            key={`outer-${i}`}
            cx={halfW + pos.dx}
            cy={halfH + pos.dy}
            size={R}
            letter={letter}
            isCenter={false}
            onTap={() => onTapLetter(letter)}
            accent={accent}
          />
        );
      })}
      {/* Center hex */}
      <Hex
        cx={halfW}
        cy={halfH}
        size={R}
        letter={puzzle.center_letter}
        isCenter
        onTap={() => onTapLetter(puzzle.center_letter)}
        accent={accent}
      />
    </svg>
  );
}

interface HexProps {
  cx: number;
  cy: number;
  size: number;
  letter: string;
  isCenter: boolean;
  onTap: () => void;
  accent: string;
}

/** A single pointy-top hexagon, click-able. */
function Hex({ cx, cy, size, letter, isCenter, onTap, accent }: HexProps) {
  // Pointy-top hexagon vertices at angles 90°, 150°, 210°, 270°, 330°, 30°
  // (one vertex straight up).
  const points = useMemo(() => {
    const angles = [90, 150, 210, 270, 330, 30];
    return angles
      .map((deg) => {
        const rad = (deg * Math.PI) / 180;
        // Note: SVG y-axis points down, so we *subtract* sin to get
        // "up = negative". Using `-sin` gives the geometrically intuitive
        // result (vertex at top has the smallest y).
        const x = cx + size * Math.cos(rad);
        const y = cy - size * Math.sin(rad);
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  }, [cx, cy, size]);

  return (
    <g
      onClick={onTap}
      onMouseDown={(e) => e.preventDefault()} // don't steal focus
      style={{ cursor: "pointer" }}
      data-testid={`bee-hex-${letter}`}
      data-center={isCenter ? "true" : "false"}
    >
      <polygon
        points={points}
        fill={isCenter ? accent : "#f4f1ea"}
        stroke={isCenter ? accent : "#d6d3c8"}
        strokeWidth={1.5}
        style={{ transition: "fill 120ms ease, transform 120ms ease" }}
      />
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={size * 0.6}
        fontWeight={700}
        fill={isCenter ? "#fff" : "#1a1a1a"}
        style={{
          fontFamily:
            'var(--font-sans), ui-sans-serif, system-ui, sans-serif',
          pointerEvents: "none",
        }}
      >
        {letter}
      </text>
    </g>
  );
}
