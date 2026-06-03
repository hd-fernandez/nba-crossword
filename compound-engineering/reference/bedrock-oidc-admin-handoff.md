# Bedrock OIDC — admin handoff (run-this-and-the-cron-works)

**For:** someone with IAM admin on AWS account `042122908126` (the `nba-bedrock` account).
**Why you're getting this:** the `nba-crossword` daily-puzzle GitHub Action generates
crossword clues with Claude on Bedrock. The runner has no AWS session, so it assumes a
dedicated IAM role via GitHub OIDC (no long-lived keys). **The role doesn't exist yet**,
so the cron has failed every morning with `Could not load credentials from any providers`.
The repo owner (Henry, `Data-Strategy-Team-Access` SSO) has no IAM permissions and cannot
create it. This is the one task that needs you.

**Time:** ~5 minutes, copy-paste. Everything is least-privilege and scoped to this one repo.

---

## Run these four blocks in order

### 1. Register GitHub as an OIDC provider (skip if already present)

Check first:
```bash
aws iam list-open-id-connect-providers \
  | grep -q token.actions.githubusercontent.com && echo "ALREADY EXISTS — skip step 1" || echo "not present — run step 1"
```

If not present:
```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. Create the role (trust scoped to this repo + main branch only)

```bash
cat > /tmp/trust-policy.json <<'JSON'
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
        "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
        "StringLike": { "token.actions.githubusercontent.com:sub": "repo:hd-fernandez/nba-crossword:ref:refs/heads/main" }
      }
    }
  ]
}
JSON

aws iam create-role \
  --role-name nba-mini-github-bedrock \
  --assume-role-policy-document file:///tmp/trust-policy.json \
  --max-session-duration 3600
```

### 3. Attach the least-privilege Bedrock-invoke policy

```bash
cat > /tmp/bedrock-invoke.json <<'JSON'
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
JSON

aws iam put-role-policy \
  --role-name nba-mini-github-bedrock \
  --policy-name bedrock-invoke \
  --policy-document file:///tmp/bedrock-invoke.json
```

### 4. Report the role ARN back to Henry

```bash
aws iam get-role --role-name nba-mini-github-bedrock --query 'Role.Arn' --output text
# expected: arn:aws:iam::042122908126:role/nba-mini-github-bedrock
```

Send that ARN to Henry. **You're done.**

---

## Henry's side (after the admin reports the ARN — no AWS access needed)

```bash
gh variable set AWS_BEDROCK_ROLE_ARN \
  --repo hd-fernandez/nba-crossword \
  --body "arn:aws:iam::042122908126:role/nba-mini-github-bedrock"

# Verify end-to-end with a forced backfill:
gh workflow run "Daily Puzzle" --repo hd-fernandez/nba-crossword -f date=2026-06-03 -f force=true
gh run watch --repo hd-fernandez/nba-crossword
```

Success = the "Configure AWS credentials" step is green and the generate step shows
`200 OK` POSTs to `bedrock-runtime.us-east-1.amazonaws.com`.

---

## Notes

- **Model access:** the pipeline calls the region-prefixed inference profile
  `us.anthropic.claude-sonnet-4-6` (not the bare foundation-model ID). The policy in step 3
  allows both the profile ARN and the underlying model ARN; if invocation 403s on the model,
  the account may need Bedrock model access enabled for Claude Sonnet in `us-east-1`.
- **`workflow_dispatch` from a non-main branch** will be denied by the step-2 trust policy
  (`sub` is pinned to `main`). To allow backfills from any branch, widen the `StringLike` to
  `repo:hd-fernandez/nba-crossword:*`. Pinned-to-main is the tighter default.
- Full background and rationale: [bedrock-oidc-setup.md](bedrock-oidc-setup.md).
