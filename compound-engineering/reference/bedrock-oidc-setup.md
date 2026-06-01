# Bedrock-via-OIDC setup for the daily-puzzle GitHub Action

**Status:** workflow code is ready ([.github/workflows/daily-puzzle.yml](../../.github/workflows/daily-puzzle.yml)). The AWS-side IAM setup below is the **last remaining step** before the cron self-serves. It needs someone with admin on AWS account `042122908126` (the `nba-bedrock` account) — likely the Data Strategy team.

## Why this exists

The GH Actions runner has no AWS SSO session (that's a desktop-interactive login). Instead of stuffing long-lived AWS keys into GitHub secrets, we let GitHub's OIDC provider mint a short-lived token that AWS trades for temporary credentials on a dedicated IAM role. No static secrets anywhere.

## What the workflow expects

Two GitHub **repository variables** (Settings → Secrets and variables → Actions → *Variables* tab — NOT secrets, these aren't sensitive):

| Variable | Value |
| --- | --- |
| `AWS_BEDROCK_ROLE_ARN` | the ARN of the role created below, e.g. `arn:aws:iam::042122908126:role/nba-mini-github-bedrock` |
| `AWS_REGION` | `us-east-1` (optional; the workflow defaults to this) |

The workflow already declares `permissions: id-token: write`, which is what lets it request the OIDC token.

## One-time AWS setup (admin required)

### 1. Register GitHub as an OIDC identity provider

Only needed once per account. If `token.actions.githubusercontent.com` is already a registered provider, skip to step 2.

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. Create the role with a GitHub-scoped trust policy

Trust policy — **scoped to this repo and the `main` branch** so no other repo or branch can assume it (`trust-policy.json`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::042122908126:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:hd-fernandez/nba-crossword:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

```bash
aws iam create-role \
  --role-name nba-mini-github-bedrock \
  --assume-role-policy-document file://trust-policy.json \
  --max-session-duration 3600
```

> If `workflow_dispatch` backfills are run from a non-`main` branch, broaden the
> `sub` condition to `repo:hd-fernandez/nba-crossword:*`. Keeping it pinned to
> `main` is the tighter default.

### 3. Attach a least-privilege Bedrock-invoke policy

The role only needs to invoke the Claude inference profile. Permissions policy (`bedrock-invoke.json`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6",
        "arn:aws:bedrock:us-east-1:042122908126:inference-profile/us.anthropic.claude-sonnet-4-6"
      ]
    }
  ]
}
```

```bash
aws iam put-role-policy \
  --role-name nba-mini-github-bedrock \
  --policy-name bedrock-invoke \
  --policy-document file://bedrock-invoke.json
```

> Inference profiles fan out to the underlying foundation model across regions,
> so both the `inference-profile/...` and the `foundation-model/...` ARN are
> required on the `Resource` list. If invocation 403s with an access-denied on
> the model ARN, widen the foundation-model resource to include the regional
> copies (`arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6`
> plus any region the profile routes to).

### 4. Set the GitHub variable

```bash
gh variable set AWS_BEDROCK_ROLE_ARN \
  --repo hd-fernandez/nba-crossword \
  --body "arn:aws:iam::042122908126:role/nba-mini-github-bedrock"
```

## Verifying

Trigger the workflow by hand once the role exists:

```bash
gh workflow run "Daily Puzzle" --repo hd-fernandez/nba-crossword \
  -f date=2026-05-28 -f force=true
gh run watch --repo hd-fernandez/nba-crossword
```

The "Configure AWS credentials" step should succeed and the generate step should show `200 OK` POSTs to `bedrock-runtime.us-east-1.amazonaws.com`. A no-games day exits clean with nothing committed.

## Notes / gotchas

- **Model ID:** Bedrock rejects the bare foundation-model ID for on-demand calls. The pipeline uses the region-prefixed inference-profile ID `us.anthropic.claude-sonnet-4-6` (`BEDROCK_DEFAULT_MODEL` in `pipeline/nba_mini/clues.py`). The IAM policy must allow that profile ARN.
- **Old secret retired:** `ANTHROPIC_API_KEY` is no longer referenced by the workflow. It can be deleted from repo secrets once this is confirmed working.
- **Reddit:** the cron also depends on the RSS ingest (no auth) — already shipped, so no secret needed there.
- **The `nba-bedrock` SSO profile** Henry uses locally is a *different* principal from this CI role; they don't share credentials. Local runs keep using SSO; CI uses this role.
