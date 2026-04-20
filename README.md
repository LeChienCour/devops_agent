# FinOps Agent

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/diegosandoval/devops_agent/actions/workflows/ci.yml/badge.svg)](https://github.com/diegosandoval/devops_agent/actions/workflows/ci.yml)

Autonomous FinOps agent for AWS cost waste detection using LangGraph + Amazon Bedrock.

> Built for **AWS Community Day 2026** — demonstrates how a small LangGraph agent backed by
> Claude on Amazon Bedrock can autonomously detect cost leaks across an AWS account, reason
> about the evidence, and propose actionable remediations with dollar-impact estimates.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     TRIGGERS                                │
│  EventBridge (cron semanal)  │  API Gateway (on-demand)     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              AGENT RUNTIME (Lambda)                         │
│                                                             │
│   ┌──────────────────────────────────────────────────┐     │
│   │          LangGraph StateGraph                    │     │
│   │                                                  │     │
│   │   [plan] → [gather] → [analyze] → [recommend]    │     │
│   │      ↑                                  │        │     │
│   │      └──────── loop si needs_more_data ─┘        │     │
│   └──────────────────────────────────────────────────┘     │
│                      │                                      │
│                      ▼                                      │
│   ┌──────────────────────────────────────────────────┐     │
│   │    Amazon Bedrock (Claude Sonnet 4.5)            │     │
│   └──────────────────────────────────────────────────┘     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼ (MCP protocol)
┌─────────────────────────────────────────────────────────────┐
│                   MCP SERVERS                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │Cost Explorer│ │ CloudWatch  │ │Trusted Adv. │            │
│  └─────────────┘ └─────────────┘ └─────────────┘            │
│  ┌─────────────┐ ┌─────────────┐                            │
│  │   GitHub    │ │EC2/VPC/EBS  │                            │
│  │ (read-only) │ │  (boto3)    │                            │
│  └─────────────┘ └─────────────┘                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                      OUTPUT                                 │
│  DynamoDB (histórico)  │  SNS → Slack  │  S3 (reportes)     │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

The agent detects eight categories of AWS cost waste, each producing a structured finding with
severity, estimated monthly impact in USD, remediation command/IaC, and LLM-generated context.

| # | Leak Type                     | Detection Signal                                   | Typical Saving/Month |
|---|-------------------------------|----------------------------------------------------|----------------------|
| 1 | NAT Gateway idle              | `BytesOutToDestination` < threshold over 7 days   | $32 + data transfer  |
| 2 | EBS volumes unattached        | `describe-volumes` state=available + age > 30 d   | $0.10 / GB           |
| 3 | EBS gp2 → gp3 migration       | `describe-volumes` type=gp2                        | ~20% of EBS spend    |
| 4 | Elastic IPs not associated    | `describe-addresses` InstanceId=null               | $3.60 each           |
| 5 | Orphaned snapshots            | `describe-snapshots` + source volume deleted       | $0.05 / GB           |
| 6 | Lambda oversized memory       | CloudWatch Insights: max_used / allocated < 40%   | 40–70% of Lambda cost|
| 7 | Log Groups without retention  | `describe-log-groups` retentionInDays=null         | $0.03 / GB / month   |
| 8 | Stopped EC2 + attached EBS    | `describe-instances` state=stopped + age > 30 d   | Cost of attached EBS |

---

## Tech Stack

| Layer            | Technology                          |
|------------------|-------------------------------------|
| Agent runtime    | AWS Lambda (Python 3.12)            |
| Orchestration    | LangGraph StateGraph                |
| LLM              | Amazon Bedrock — Claude Sonnet 4.5  |
| Tool protocol    | MCP (Model Context Protocol)        |
| AWS SDK          | boto3 + aws-lambda-powertools       |
| Data validation  | Pydantic v2 + pydantic-settings     |
| Persistence      | DynamoDB                            |
| Notifications    | SNS → Slack webhook                 |
| IaC              | Terraform >= 1.6                    |
| Linter/Formatter | Ruff                                |
| Type checker     | Mypy (strict)                       |
| Test framework   | pytest + moto                       |

---

## Quickstart

> Coming soon after Phase 1 (Terraform infrastructure base).

Full setup instructions including `terraform apply` and `make deploy` will be documented in
`docs/SETUP.md` once the infrastructure module is complete.

---

## Project Structure

```
.
├── src/
│   ├── agent/           # LangGraph graph, nodes, prompts, Pydantic models
│   ├── mcp_servers/     # MCP server implementations (Cost Explorer, CloudWatch, …)
│   ├── common/          # Shared utilities: Bedrock client, AWS factories, config
│   └── notifications/   # Slack formatter, DynamoDB writer
├── tests/
│   ├── unit/            # Fully mocked unit tests
│   ├── integration/     # moto-backed integration tests
│   └── fixtures/        # JSON response fixtures
├── infra/               # Terraform modules
├── scripts/             # Local runner, demo seeding, report generator
├── docs/                # Architecture, setup, demo script, comparison
├── pyproject.toml       # Build system, dependencies, tool config
├── Makefile             # Developer workflow targets
├── PLAN.md              # Master build plan (source of truth for Claude Code)
└── CLAUDE.md            # Conventions and instructions for Claude Code
```

---

## Development

```bash
# Install dependencies
make install

# Lint and format check
make lint

# Auto-format
make format

# Type check
make typecheck

# Run unit tests
make test

# Run all tests with coverage
make test-all
```

---

## Contributing

This project follows the phased build plan described in [`PLAN.md`](PLAN.md).

- Branch naming: `feat/fase-N-description`
- Commit format: Conventional Commits in English, e.g. `feat(agent): implement plan node [Phase 2]`
- No direct commits to `main` — all changes go through a PR
- See [`CLAUDE.md`](CLAUDE.md) for the full conventions reference

---

## License

[MIT](LICENSE) — Diego Sandoval, 2026
