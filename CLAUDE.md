# nba-crossword Working Instructions

A daily NBA-themed mini crossword app. Clues refresh nightly from the previous day's NBA slate.

## Context-engineering artifact paths

The compound-engineering plugin skills (`ce-plan`, `ce-brainstorm`, `ce-code-review`, `ce-compound`, `ce-doc-review`, and related) reference `docs/plans/`, `docs/brainstorms/`, `docs/reviews/`, `docs/solutions/` as defaults. In this project, those paths are overridden. Always substitute:

| Skill default | This project |
| --- | --- |
| `docs/plans/` | `compound-engineering/plans/` |
| `docs/brainstorms/` | `compound-engineering/brainstorms/` |
| `docs/reviews/` | `compound-engineering/reviews/` |
| `docs/solutions/` | `compound-engineering/solutions/` |

Do NOT create a `docs/` folder at the repo root.

Project-specific artifact paths (no skill equivalent):

- Reference snapshots: `compound-engineering/reference/`
- Templates: `compound-engineering/templates/`
- Analyses: `compound-engineering/analyses/`
- Todos: `compound-engineering/todos/`

## How to Work

- Read existing code before changing it.
- Make a plan first; don't code immediately unless explicitly asked.
- Prefer small, safe, reviewable changes.
- Commit often.

## Project Rules

(To be filled in as design decisions are made — stack choices, data sources, deployment target, etc.)
