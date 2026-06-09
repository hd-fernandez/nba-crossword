#!/bin/bash
# Local daily-puzzle generator — the laptop stopgap for the GitHub cron.
#
# Why this exists: the GitHub Action can't authenticate to Bedrock (the AWS-side
# OIDC/IAM setup needs an admin Henry doesn't have — see
# compound-engineering/reference/bedrock-oidc-admin-handoff.md). This script runs
# the same generation locally, where the `nba-bedrock` SSO profile already has
# Bedrock access. NOTE: this SSO token has NO refresh token (verified 2026-06-04;
# `refreshToken: false` in ~/.aws/sso/cache) — the access token is short-lived
# (~hours) and CANNOT self-refresh unattended. When it lapses, the only renewal
# is an interactive `aws sso login --profile nba-bedrock` (browser). The
# preflight below fails loud with that exact instruction. See
# compound-engineering/solutions/2026-06-04-sso-token-no-refresh-unattended-jobs.md
#
# Scheduling is currently PAUSED (launchd agent unloaded) — generation is manual.
# Manual run:  aws sso login --profile nba-bedrock   # only if the token lapsed
#              scripts/daily-puzzle-local.sh
# Backfill:    scripts/daily-puzzle-local.sh 2026-06-02 --force

set -uo pipefail

# --- Config -----------------------------------------------------------------
REPO="/Users/HFernandez/Developer/nba-crossword"
PIPELINE="${REPO}/pipeline"
export AWS_PROFILE="nba-bedrock"
export AWS_REGION="us-east-1"
export NBA_MINI_LLM_BACKEND="bedrock"
# Make the toolchain reachable when launchd runs us with a bare PATH.
# uv lives in miniconda's bin on this machine; aws/git/gh in homebrew + system.
export PATH="/Users/HFernandez/miniconda3/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

# Optional args: <date> and/or --force (same shape as the workflow_dispatch inputs).
DATE_ARG=""
FORCE_ARG=""
for a in "$@"; do
  case "$a" in
    --force) FORCE_ARG="--force" ;;
    [0-9]*) DATE_ARG="$a" ;;
  esac
done

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

cd "${PIPELINE}" || { log "FATAL: pipeline dir missing: ${PIPELINE}"; exit 1; }

# --- Preflight: confirm we can actually reach AWS (forces SSO auto-refresh) --
if ! aws sts get-caller-identity --query Arn --output text >/dev/null 2>&1; then
  log "FATAL: no usable AWS credentials for profile '${AWS_PROFILE}'."
  log "       The SSO refresh chain has lapsed. Run: aws sso login --profile ${AWS_PROFILE}"
  exit 1
fi
log "AWS auth OK ($(aws sts get-caller-identity --query Arn --output text 2>/dev/null))"

# Shared args. The crossword takes --backend (Bedrock); the Bee does NOT
# (it's corpus-driven — no LLM, no Bedrock), so it gets its own arg set.
base_args=(--out ../puzzles)
[ -n "${DATE_ARG}" ]  && base_args+=(--date "${DATE_ARG}")
[ -n "${FORCE_ARG}" ] && base_args+=(--force)

# --- Generate crosswords (both leagues, per-league isolation) ---------------
rc=0
for league in nba wnba; do
  log "generate crossword: ${league}"
  if ! uv run python -m nba_mini.generate --league "${league}" --backend bedrock "${base_args[@]}"; then
    log "ERROR: ${league} crossword generation failed"
    rc=1
  fi
done

# --- Generate Spelling Bees (corpus-driven; runs regardless of crossword rc) -
for league in nba wnba; do
  log "generate bee: ${league}"
  if ! uv run python -m nba_mini.bee.generate_cli --league "${league}" "${base_args[@]}"; then
    log "ERROR: ${league} Bee generation failed"
    rc=1
  fi
done

# --- Commit + push whatever landed ------------------------------------------
cd "${REPO}" || { log "FATAL: repo dir missing"; exit 1; }
if [ -z "$(git status --porcelain puzzles/)" ]; then
  log "No puzzle changes (no-games day, or idempotent re-run). Nothing to commit."
  exit "${rc}"
fi

git add puzzles/
STAGED="$(git diff --name-only --cached -- 'puzzles/**/*.json')"
if [ -z "${STAGED}" ]; then
  log "puzzles/ changed but no JSON staged — refusing to commit."
  exit 1
fi
DATE="$(basename "$(echo "${STAGED}" | head -n 1)" .json)"
LEAGUES="$(echo "${STAGED}" | sed -E 's#puzzles/([^/]+)/.*#\1#' | sort -u | paste -sd '+' -)"

git commit -m "chore(puzzles): add ${DATE} (${LEAGUES}) [local]"
if git push; then
  log "pushed ${DATE} (${LEAGUES})"
else
  log "ERROR: git push failed — commit is local only"
  rc=1
fi

exit "${rc}"
