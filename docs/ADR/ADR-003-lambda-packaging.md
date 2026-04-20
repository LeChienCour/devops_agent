# ADR-003: Lambda Packaging — ZIP vs Container Image

**Status:** Accepted (ZIP for now; revisit at Phase 3)  
**Date:** 2026-04-20  
**Deciders:** Diego Sandoval

---

## Context

LangGraph + langchain-aws + boto3 + mcp + aws-lambda-powertools + structlog will push the unzipped deployment size toward the 250 MB Lambda ZIP limit. Container images support up to 10 GB and enable Lambda SnapStart-equivalent warmup strategies.

## Decision

**Start with ZIP packaging** through Phase 2. Evaluate at Phase 3 (MCP servers added).

**Threshold for switching to container image:** unzipped size > 200 MB OR cold start > 5s in benchmarks.

### ZIP optimizations to apply first
- Use Lambda layers for heavy deps (`boto3`, `langchain-aws`) — boto3 is already provided by Lambda runtime.
- `--slim` builds via `pip install --no-compile`.
- Strip `.dist-info`, tests, and type stubs from vendor packages in Makefile `build` target.

### If container image needed
- Base image: `public.ecr.aws/lambda/python:3.12`
- Multi-stage build to minimize image size
- Push to ECR in `infra/modules/agent_lambda/`

## Consequences

- **Positive (ZIP):** Simpler Terraform, faster CI deploy, no ECR cost.
- **Positive (Container):** No size limit, pre-warmed layers, exact reproducibility.
- **Decision point:** Measure at Phase 3. Do not prematurely optimize.
