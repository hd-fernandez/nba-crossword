---
title: AWS SSO tokens with no refresh token can't drive an unattended job — the real cron blocker
date: 2026-06-04
category: solutions
module: scripts/daily-puzzle-local
problem_type: integration_issue
component: infrastructure
severity: high
symptoms:
  - "Scheduled local job (launchd) fails most mornings with 'no usable AWS credentials for profile nba-bedrock'"
  - "aws sts get-caller-identity works when you run it by hand, but the 9:30 scheduled run fails"
  - "Bedrock clue generation dies before writing any puzzle; CI cron also red every morning"
root_cause: missing_config
resolution_type: workaround
tags: [aws, sso, bedrock, oidc, launchd, cron, auth, unattended, scheduling]
---

# AWS SSO with no refresh token can't sustain an unattended job

## Problem

The daily puzzle generator authenticates to Amazon Bedrock through an AWS SSO
profile (`nba-bedrock`). A scheduled local `launchd` job kept failing most
mornings with `no usable AWS credentials for profile 'nba-bedrock'`, even though
running the same script by hand minutes later worked. Two different "cron is
broken" emails (the GitHub Actions cron *and* the local job) were really **one
root cause: the SSO session can't renew itself unattended.**

## Symptoms

- `launchd` run at 9:30 fails: `FATAL: no usable AWS credentials`.
- Run it by hand at 10:00 and `aws sts get-caller-identity` succeeds — looks
  intermittent / flaky, but isn't.
- The GitHub Actions cron is *also* red every morning, but for a **different**
  reason (see Don't-Conflate below).

## Root Cause

Inspect the SSO token cache (`~/.aws/sso/cache/*.json`):

- The **long-lived client registration** (expires ~weeks out, e.g. `2026-07-22`)
  has `clientId`/registration but **`refreshToken: false`**.
- The **usable access token** is short-lived (hours, e.g. expires
  `2026-06-04T15:05:50Z`) and there is **no refresh token** anywhere in the
  cache to mint a new one.

So once the short-lived access token expires (every few hours), the only way to
get a new one is an **interactive** `aws sso login` (opens a browser). An
unattended scheduler hitting a window where the token has lapsed has no way to
self-heal — there's nothing to refresh *with*. "Laptop awake at 9:30" is
necessary but **not sufficient**; the token also has to be live at that instant,
and nothing keeps it live.

## What Didn't Work

- **Assuming SSO refreshes non-interactively.** An earlier session claimed the
  refresh chain would renew silently. It won't, *for this registration* —
  because there is no refresh token. Verify the cache; don't assume.
- **A local `launchd` schedule as the durable fix.** It papers over CI but
  inherits the same auth ceiling: any morning the token is lapsed, the job dies.

## Solution (current posture: manual)

Paused all scheduling. Generate by hand, priming auth first when needed:

```sh
aws sso login --profile nba-bedrock                 # ~10s, browser; only if lapsed
cd ~/Developer/nba-crossword && scripts/daily-puzzle-local.sh   # yesterday's slate
```

The script fails loud with that exact instruction when the token is dead, so a
lapsed run never ships an empty/garbage puzzle — it just stops.

## The two durable fixes (when time allows)

1. **GitHub OIDC (the real hands-off path).** CI assumes an IAM role via OIDC —
   no long-lived secret, no token to expire. Blocked on an AWS IAM admin for
   account `042122908126`; runbook in
   `compound-engineering/reference/bedrock-oidc-admin-handoff.md`, then
   `gh variable set AWS_BEDROCK_ROLE_ARN ...`.
2. **A longer-lived local credential** (e.g. an IAM user/role with static or
   auto-refreshing creds for the batch box) — removes the interactive-login
   requirement from the local schedule.

## Don't conflate the two red crons

This is the trap that cost time: **two failing schedules, two different causes.**

- **GitHub Actions cron** fails because `AWS_BEDROCK_ROLE_ARN` is unset / the
  OIDC role was never created (it can't auth at all). Known, expected, parked.
- **Local launchd job** fails because the SSO access token lapsed and can't
  refresh unattended (this doc).

Fixing one does nothing for the other. The morning the NBA Finals Game 1 puzzle
was missing, *both* fired — plus an unrelated ingest crash
([[2026-06-03-nba-scoreboard-pts-unreliable]]). Triage each signal to its own
cause before acting.

## Prevention

- **Before promising an unattended job will "self-heal," check the token cache
  for a refresh token.** No `refreshToken` → it can't, full stop. SSO is not
  uniformly refreshable; it depends on the registration.
- **For unattended workloads, prefer OIDC role assumption or a long-lived
  credential over interactive SSO.** Interactive SSO is for humans at keyboards.
- **When two scheduled jobs both go red, suspect two causes, not one.** Read
  each failure message to its own root before assuming a shared fix.

## Related Issues

- [[2026-06-03-nba-scoreboard-pts-unreliable]] — the ingest-crash half of the
  same Finals-morning incident
- [[2026-06-03-verify-before-you-claim]] — "verify, don't assume" (here: verify
  the token cache rather than assume SSO refreshes)
