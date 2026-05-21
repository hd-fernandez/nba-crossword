"""Canonical puzzle JSON schema. Mirrored on the TypeScript side in web/lib/puzzle.ts.

The grid is the source of truth for letter placement; entries carry the same letters
as `answer` for downstream convenience (clue prompts, analytics). The validator
enforces agreement between the two.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GRID_SIZE = 5
Voice = Literal["wry", "discoursey", "factual"]
Direction = Literal["across", "down"]


class LetterCell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: Annotated[str, Field(pattern=r"^[A-Z]$")]


class BlockCell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block: Literal[True]


Cell = LetterCell | BlockCell


class Grid(BaseModel):
    model_config = ConfigDict(extra="forbid")
    size: Literal[5]
    cells: list[list[Cell]]

    @model_validator(mode="after")
    def _square_grid(self) -> "Grid":
        if len(self.cells) != self.size:
            raise ValueError(f"grid must have {self.size} rows, got {len(self.cells)}")
        for r, row in enumerate(self.cells):
            if len(row) != self.size:
                raise ValueError(f"row {r} must have {self.size} cells, got {len(row)}")
        return self


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    direction: Direction
    row: int = Field(ge=0, lt=GRID_SIZE)
    col: int = Field(ge=0, lt=GRID_SIZE)
    answer: Annotated[str, Field(pattern=r"^[A-Z]+$", min_length=2, max_length=GRID_SIZE)]
    clue: Annotated[str, Field(min_length=1, max_length=160)]
    voice: Voice


class Puzzle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    # Sequential count since launch (1-indexed). Frontend renders this as
    # "NBA Mini #N" on the splash screen. Pipeline computes it as the count
    # of existing real puzzle files + 1.
    puzzle_number: int = Field(ge=1)
    grid: Grid
    entries: list[Entry]
    season_context_version: str
    generated_at: datetime
    model: str

    @model_validator(mode="after")
    def _entries_match_grid(self) -> "Puzzle":
        cells = self.grid.cells
        seen_starts: set[tuple[int, int, Direction]] = set()
        for entry in self.entries:
            start_key = (entry.row, entry.col, entry.direction)
            if start_key in seen_starts:
                raise ValueError(f"duplicate entry start at {start_key}")
            seen_starts.add(start_key)

            for i, letter in enumerate(entry.answer):
                r = entry.row + (i if entry.direction == "down" else 0)
                c = entry.col + (i if entry.direction == "across" else 0)
                if r >= GRID_SIZE or c >= GRID_SIZE:
                    raise ValueError(
                        f"entry {entry.id} ({entry.answer}) runs off the grid at ({r},{c})"
                    )
                cell = cells[r][c]
                if isinstance(cell, BlockCell):
                    raise ValueError(
                        f"entry {entry.id} ({entry.answer}) crosses block at ({r},{c})"
                    )
                if cell.answer != letter:
                    raise ValueError(
                        f"entry {entry.id} letter {i} expects {letter!r}, "
                        f"grid has {cell.answer!r} at ({r},{c})"
                    )

            # The cell before the entry's start must be a block or off-grid;
            # otherwise this isn't really the start of an entry.
            before_r = entry.row - (1 if entry.direction == "down" else 0)
            before_c = entry.col - (1 if entry.direction == "across" else 0)
            if 0 <= before_r < GRID_SIZE and 0 <= before_c < GRID_SIZE:
                before = cells[before_r][before_c]
                if isinstance(before, LetterCell):
                    raise ValueError(
                        f"entry {entry.id} does not start at the head of its run "
                        f"(letter cell precedes it at ({before_r},{before_c}))"
                    )

            # The cell after the entry's last letter must be a block or off-grid.
            end_i = len(entry.answer)
            after_r = entry.row + (end_i if entry.direction == "down" else 0)
            after_c = entry.col + (end_i if entry.direction == "across" else 0)
            if 0 <= after_r < GRID_SIZE and 0 <= after_c < GRID_SIZE:
                after = cells[after_r][after_c]
                if isinstance(after, LetterCell):
                    raise ValueError(
                        f"entry {entry.id} does not end at the tail of its run "
                        f"(letter cell follows it at ({after_r},{after_c}))"
                    )

        # Every letter cell must be covered by at least one across and one down entry.
        across_covered: set[tuple[int, int]] = set()
        down_covered: set[tuple[int, int]] = set()
        for entry in self.entries:
            for i in range(len(entry.answer)):
                r = entry.row + (i if entry.direction == "down" else 0)
                c = entry.col + (i if entry.direction == "across" else 0)
                if entry.direction == "across":
                    across_covered.add((r, c))
                else:
                    down_covered.add((r, c))

        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if isinstance(cells[r][c], LetterCell):
                    if (r, c) not in across_covered:
                        raise ValueError(f"cell ({r},{c}) is not part of any across entry")
                    if (r, c) not in down_covered:
                        raise ValueError(f"cell ({r},{c}) is not part of any down entry")

        return self
