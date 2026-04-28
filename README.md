# FinOps Agent

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/diegosandoval/devops_agent/actions/workflows/ci.yml/badge.svg)](https://github.com/diegosandoval/devops_agent/actions/workflows/ci.yml)

> **Build status:** Phases 0–8 complete — repo setup, Terraform infra, LangGraph agent core, 12 AWS tools + MCP wrappers, DynamoDB persistence, eval harness, Infracost in CI, Slack Block Kit notifications, Markdown report generator, demo leak seeding, talk documentation, CloudWatch metrics + hardening. **Ready for AWS Community Day 2026.**

Autonomous FinOps agent for AWS cost waste detection using LangGraph + Amazon Bedrock.

> Built for **AWS Community Day 2026** — demonstrates how a small LangGraph agent backed by
> Claude on Amazon Bedrock can autonomously detect cost leaks across an AWS account, reason
> about the evidence, and propose actionable remediations with dollar-impact estimates.

---

## Agent Graph

```
                    ┌─────────┐
         trigger ──▶│  plan   │  LLM generates investigation plan (tools + date range)
                    └────┬────┘
                         │
                    ┌────▼────┐
              ┌─────│  gather │  Executes AWS tools in-process (boto3)
              │     └────┬────┘
              │          │
              │     ┌────▼────┐
              └─────│ analyze │  LLM identifies anomalies, decides if more data needed
    needs_more_data └────┬────┘
                         │ done
                    ┌────▼────────┐
                    │  recommend  │  LLM produces structured Finding[] + Recommendation
                    └─────────────┘
```

Guardrails enforced at every loop: max iterations (5), max tokens (50k), Bedrock cost ceiling ($0.50/run).

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
| Tool protocol    | In-process tools `agent/tools/` (Lambda) + MCP wrappers `mcp_servers/` (demo/CLI) |
| AWS SDK          | boto3 + aws-lambda-powertools       |
| Data validation  | Pydantic v2 + pydantic-settings     |
| Persistence      | DynamoDB                            |
| Notifications    | SNS → Slack webhook                 |
| IaC              | Terraform >= 1.6                    |
| Linter/Formatter | Ruff                                |
| Type checker     | Mypy (strict)                       |
| Test framework   | pytest + moto                       |

---

## Quickstart (5 minutes)

> Prerequisites: Python 3.12, Terraform >= 1.6, AWS credentials with Cost Explorer + EC2 + CloudWatch read access, Bedrock model access enabled for `anthropic.claude-sonnet-4-5` in `us-east-1`.

```bash
# 1. Clone and install deps
git clone https://github.com/diegosandoval/devops_agent.git
cd devops_agent
make install

# 2. Copy and fill env vars
cp .env.example .env
# Edit .env: add SLACK_WEBHOOK_URL (optional) and verify AWS region

# 3. Deploy agent infrastructure (Lambda + DynamoDB + SNS + EventBridge)
make tf-init && make tf-apply

# 4. Build and deploy Lambda package
make deploy

# 5. (Optional) Seed intentional cost leaks for testing
make seed-demo

# 6. Trigger an on-demand investigation
make invoke
# → prints investigation_id, findings_count, total_savings_usd, bedrock_cost_usd

# 7. Generate a Markdown report from findings
python scripts/generate_report.py --investigation-id <id-from-step-6>

# 8. Clean up demo leaks
make cleanup-demo
```

### Demo mode (live demo / recording)

```bash
make seed-demo     # seed leaks once at the start
make invoke        # run investigation (repeat for each take)
make logs          # tail CloudWatch logs in real-time during invoke
make cleanup-demo  # destroy demo resources at the end
```

Full live demo script with backup plans: [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)

---

## Project Structure

```
.
├── src/
│   ├── agent/
│   │   ├── tools/          # In-process tool functions — TOOL_REGISTRY (12 tools)
│   │   │   ├── cost_explorer.py, cloudwatch.py, ec2_inventory.py, trusted_advisor.py
│   │   ├── nodes/          # LangGraph nodes: plan, gather, analyze, recommend
│   │   ├── prompts/        # System + node prompts as versioned .md files
│   │   ├── models/         # Pydantic v2: Finding, Recommendation, Investigation
│   │   ├── guardrails.py   # Iteration / token / Bedrock cost limits per run
│   │   ├── state.py        # AgentState TypedDict
│   │   ├── graph.py        # LangGraph StateGraph (build_graph)
│   │   └── handler.py      # Lambda entrypoint
│   ├── mcp_servers/        # FastMCP wrappers for demo/CLI — zero logic, import from tools/
│   ├── common/
│   │   ├── config.py       # Pydantic-settings (env vars, no secrets)
│   │   ├── secrets.py      # SSM Parameter Store fetcher with cache
│   │   ├── bedrock_client.py  # ChatBedrockConverse + tenacity retry
│   │   ├── aws_clients.py  # boto3 client factory
│   │   └── logger.py       # structlog (JSON prod / Console local)
│   └── notifications/      # dynamodb_writer.py + slack_notifier.py (Block Kit)
├── tests/
│   ├── unit/            # 82 tests, fully mocked — no external calls
│   ├── integration/     # 21 moto-backed tests (EC2, CloudWatch)
│   └── fixtures/        # JSON fixtures (cost_explorer, plan, analyze, ec2_inventory, findings)
├── evals/               # False-positive measurement harness — rule-based, no external calls
├── infra/               # Agent Terraform root (storage, lambda, eventbridge, SNS)
│   ├── demo/            # Independent Terraform root — seed_leaks only
│   └── modules/         # Reusable modules (storage, agent_lambda, notifications, …)
├── docs/
│   └── ADR/             # Architecture Decision Records (001-MCP, 002-DynamoDB, 003-Lambda)
├── scripts/             # run_local.py, generate_report.py (Markdown from DynamoDB), demo seeding
├── pyproject.toml       # Build system, dependencies, ruff + mypy config
├── Makefile             # Developer + infra workflow targets
├── PLAN.md              # Master build plan (source of truth for Claude Code)
└── CLAUDE.md            # Conventions and instructions for Claude Code
```

---

## Development

```bash
make install       # Install all dependencies (uv or pip fallback)
make lint          # ruff check + ruff format --check
make format        # Auto-fix formatting and lint issues
make typecheck     # mypy strict
make test          # Unit tests only (fast, no AWS calls)
make test-all      # Full suite with coverage report

# Lambda
make build         # Build Lambda zip (manylinux2014 wheels, macOS-safe)
make deploy        # Build + upload Lambda to AWS
make invoke        # Trigger on-demand investigation
make logs          # Tail CloudWatch logs (live stream)

# Evals
python evals/false_positive_rate.py   # Rule-based FP rate against fixtures

# Infra
make tf-init       # terraform init (agent infra)
make tf-plan       # terraform plan
make tf-apply      # terraform apply
make tf-destroy    # terraform destroy
make seed-demo     # Deploy intentional leak resources for demo
make cleanup-demo  # Destroy demo leak resources
```

> **Infracost** runs automatically on every PR that touches `infra/` — posts a cost diff comment.
> Requires `INFRACOST_API_KEY` secret in GitHub repo settings (free at [cloud.infracost.io](https://cloud.infracost.io)).

---

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Extended architecture — Mermaid diagrams, tool registry, data model, security |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | Live demo guide — minute-by-minute script, backup plans, pre-demo checklist |
| [`docs/COMPARISON.md`](docs/COMPARISON.md) | DIY vs AWS managed tools vs FinOps Agent — cost and capability comparison |
| [`docs/ADR/`](docs/ADR/) | Architecture Decision Records (MCP topology, DynamoDB schema, Lambda packaging) |

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
