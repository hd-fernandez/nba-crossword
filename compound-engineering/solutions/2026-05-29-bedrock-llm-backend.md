---
title: Reaching Claude via Amazon Bedrock instead of Snowflake/direct API
date: 2026-05-29
category: solutions
module: pipeline/nba_mini/clues
problem_type: tooling_decision
component: tooling
severity: high
applies_when:
  - "Org blocks personal Anthropic API keys or Snowflake Cortex keypairs"
  - "AWS SSO is already configured and Bedrock has Claude access enabled"
  - "A pipeline needs Claude but the auth story is the blocker, not the code"
tags: [bedrock, llm, aws-sso, auth, inference-profile]
---

# Reaching Claude via Amazon Bedrock instead of Snowflake/direct API

## Context

The pipeline needed real Claude calls for clue generation. Two paths were blocked or painful: Snowflake Cortex (personal user couldn't `ALTER USER` to set a keypair — needed admin/service-account provisioning) and a direct Anthropic API key (not issued). A teammate's one-line answer was "use bedrock." It turned out the machine was *already* fully provisioned for it — Claude Code itself runs through Bedrock here — so there was nothing to request.

## Guidance

Claude is available through **Amazon Bedrock**, authed by the **ambient AWS credential chain** (SSO profile / env / instance role) rather than any API key. The Anthropic SDK ships a drop-in client:

```python
from anthropic import AnthropicBedrock
client = AnthropicBedrock(aws_region="us-east-1")  # creds from AWS_PROFILE / SSO
resp = client.messages.create(
    model="us.anthropic.claude-sonnet-4-6",  # NOT "anthropic.claude-sonnet-4-6"
    max_tokens=256,
    messages=[{"role": "user", "content": prompt}],
)
```

**The one gotcha that costs an hour:** Bedrock rejects the bare foundation-model ID for on-demand calls:

```
BadRequestError 400: Invocation of model ID anthropic.claude-sonnet-4-6 with
on-demand throughput isn't supported. Retry with the ID or ARN of an
inference profile that contains this model.
```

You must use the **region-prefixed inference-profile ID** (`us.anthropic.claude-sonnet-4-6`, or `global.anthropic.…`). Discover the valid IDs with:

```bash
aws bedrock list-inference-profiles --profile <profile> --region us-east-1 \
  --query "inferenceProfileSummaries[].inferenceProfileId" --output text
```

In this repo the seam is a `ClueLLM` Protocol, so the addition was a sibling class with identical request/response handling:

- `BedrockClueLLM` next to `AnthropicClueLLM` in `pipeline/nba_mini/clues.py` (both lazy-import `anthropic`; shared `_extract_text` parses the `Message.content` blocks).
- `Deps.production(backend=...)` picks `"anthropic"` vs `"bedrock"`, falling back to `$NBA_MINI_LLM_BACKEND` then `"anthropic"`.
- CLI flag `--backend bedrock`; `BEDROCK_DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"`.

## Why This Matters

The blocker was never the code — it was auth. Bedrock collapses the whole Snowflake-permissions saga into "you already have an SSO login." Recognizing that an org's existing AWS access *is* the Claude access avoids weeks of waiting on a service-account ticket. Keeping the transport behind a Protocol meant supporting it was ~40 lines plus tests, with the direct-API path untouched as a fallback.

## When to Apply

- Any time "we can't get an API key" is blocking an LLM integration but the org runs on AWS — check `aws bedrock list-foundation-models --by-provider anthropic` first.
- When Claude Code is already working in a repo via `CLAUDE_CODE_USE_BEDROCK`: the same profile/region your editor uses will work for your pipeline.

## Caveats / Follow-ups

- **Headless/CI has no SSO session.** GitHub Actions can't reuse a desktop SSO login — the cron needs an IAM role assumed via OIDC (or static creds in secrets). Local runs and the cron have different Bedrock auth stories.
- Region and model availability vary per account; don't hardcode an inference-profile ID without confirming it's listed for that account.

## Related

- [PROJECT-STATUS.md](../PROJECT-STATUS.md) — What's-left #1 (resolved), #4 (cron auth)
- Reddit 403 (What's-left #3) is the *remaining* blocker for the full daily pipeline.
