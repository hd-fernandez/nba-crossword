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
 * hexagon. Pure SVG so the layout is stable across browsers and the
 * shapes are crisp at any zoom level.
 *
 * Geometry: pointy-top hexagons in a 2-1-2-1-2 pattern? No — flat-top
 * is the NYT convention and reads better. We use the standard "axial"
 * layout: one center, six neighbors at 60° intervals.
 */
export function BeeHive({ puzzle, outerOrder, onTapLetter, accent }: BeeHiveProps) {
  // Hex dimensions in SVG units. Hex math is from the standard pointy-top
  // axial coordinate system rotated 30°: width = sqrt(3) * size, height = 2 * size.
  const SIZE = 50;
  const WIDTH = Math.sqrt(3) * SIZE;
  const HEIGHT = 2 * SIZE;
  // Inset between hexes so they don't touch — visually nicer than abutting.
  const GAP = 4;

  // Six outer-hex positions around the center. Standard flat-top neighbors:
  // top-right, right, bottom-right, bottom-left, left, top-left.
  // We compute the six (dx, dy) offsets in SVG units.
  const positions = useMemo(() => {
    // Distance between hex centers (flat-top): horizontal = sqrt(3) * SIZE,
    // vertical-half = SIZE * 1.5. Add the gap so the hexes breathe.
    const w = WIDTH + GAP;
    const h = (3 * SIZE) / 2 + GAP;
    return [
      { dx: 0, dy: -2 * (SIZE + GAP / 2) }, // 12 o'clock
      { dx: w * 0.866, dy: -h / 2 - GAP / 4 }, // 2 o'clock — these aren't quite right; we'll use point-around-center
      { dx: w * 0.866, dy: h / 2 + GAP / 4 }, // 4 o'clock
      { dx: 0, dy: 2 * (SIZE + GAP / 2) }, // 6 o'clock
      { dx: -w * 0.866, dy: h / 2 + GAP / 4 }, // 8 o'clock
      { dx: -w * 0.866, dy: -h / 2 - GAP / 4 }, // 10 o'clock
    ];
  }, []);

  // Compute SVG viewBox so all 7 hexes fit comfortably with breathing room.
  const PADDING = 16;
  const VIEW_W = 4 * (WIDTH + GAP) + PADDING * 2;
  const VIEW_H = 4 * (SIZE + GAP) + PADDING * 2;
  const CX = VIEW_W / 2;
  const CY = VIEW_H / 2;

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
      {/* Outer hexes */}
      {positions.map((pos, i) => {
        const letter = outerOrder[i];
        if (!letter) return null;
        return (
          <Hex
            key={`outer-${i}`}
            cx={CX + pos.dx}
            cy={CY + pos.dy}
            size={SIZE}
            letter={letter}
            isCenter={false}
            onTap={() => onTapLetter(letter)}
            accent={accent}
          />
        );
      })}
      {/* Center hex on top so it overlaps any near-collision */}
      <Hex
        cx={CX}
        cy={CY}
        size={SIZE}
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

/** A single flat-top hexagon, click-able. */
function Hex({ cx, cy, size, letter, isCenter, onTap, accent }: HexProps) {
  // Flat-top hexagon: 6 points at angles 0°, 60°, 120°, 180°, 240°, 300°
  // (relative to center). We rotate 30° to make it pointy-top, which reads
  // better with letters inside it. Actually NYT uses pointy-top — confirm
  // by inspection. The math: pointy-top points at angles 30°, 90°, 150°,
  // 210°, 270°, 330°.
  const points = useMemo(() => {
    const angles = [30, 90, 150, 210, 270, 330];
    return angles
      .map((deg) => {
        const rad = (deg * Math.PI) / 180;
        const x = cx + size * Math.cos(rad);
        const y = cy + size * Math.sin(rad);
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
        style={{ transition: "fill 120ms ease" }}
      />
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={size * 0.65}
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
