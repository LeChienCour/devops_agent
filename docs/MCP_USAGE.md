# Using FinOps Agent Tools via Claude Code CLI

This guide covers using the agent's AWS tools interactively from Claude Code CLI (MCP mode). This is separate from the Lambda deployment — no AWS Lambda required, tools run locally against your AWS account.

---

## Prerequisites

```bash
# 1. Install dependencies
make install

# 2. AWS credentials active in your shell
aws sts get-caller-identity   # must succeed

# 3. Claude Code CLI installed
claude --version
```

---

## Setup (one-time)

The `.claude/settings.json` file is already configured. Claude Code picks it up automatically when you open a session inside this directory:

```bash
cd /path/to/devops_agent
claude
```

Verify servers loaded:

```bash
claude mcp list
```

Expected output:
```
finops-security       running   7 tools
finops-cost           running   3 tools
finops-cloudwatch     running   3 tools
finops-ec2            running   5 tools
finops-trusted-advisor running  1 tool
```

---

## Available MCP Servers and Tools

### `finops-security` — Security Posture (7 tools)

| Tool | What it does |
|---|---|
| `list_guardduty_findings` | Active GuardDuty threats (HIGH/CRITICAL) |
| `list_config_noncompliant_rules` | AWS Config non-compliant rules + affected resources |
| `list_iam_analyzer_findings` | IAM Access Analyzer external access findings |
| `list_security_hub_findings` | Aggregated Security Hub findings |
| `get_cloudtrail_status` | Trail gaps, logging disabled, validation off |
| `list_open_security_groups` | SGs with 0.0.0.0/0 on SSH/RDP/DB ports |
| `list_iam_credential_issues` | Root MFA, root keys, users without MFA, stale keys |

### `finops-cost` — Cost Explorer (3 tools)

| Tool | What it does |
|---|---|
| `get_cost_by_service` | Monthly spend grouped by AWS service |
| `get_cost_anomalies` | Cost anomaly detection results |
| `get_cost_forecast` | Spend forecast for a date range |

### `finops-cloudwatch` — CloudWatch (3 tools)

| Tool | What it does |
|---|---|
| `get_metric_statistics` | CloudWatch metric datapoints |
| `get_cloudwatch_insights` | Logs Insights query runner |
| `list_log_groups_without_retention` | Log groups with no retention policy |

### `finops-ec2` — EC2 Inventory (5 tools)

| Tool | What it does |
|---|---|
| `list_unattached_ebs_volumes` | EBS volumes not attached to any instance |
| `list_unassociated_eips` | Elastic IPs with no associated resource |
| `list_stopped_instances` | EC2 instances stopped > 30 days |
| `list_old_snapshots` | Snapshots older than 90 days |
| `list_idle_nat_gateways` | NAT gateways with < 1 MB traffic over 7 days |

### `finops-trusted-advisor` — Trusted Advisor (1 tool)

| Tool | What it does |
|---|---|
| `list_cost_optimization_checks` | TA cost optimization checks (Business/Enterprise support required) |

---

## Example Prompts

Once `claude` is running inside this directory, use natural language — Claude Code will call the tools automatically:

```
Run a full security audit of my AWS account
```

```
Check if GuardDuty has any active HIGH or CRITICAL findings in us-east-1
```

```
List all security groups that have SSH (port 22) open to the internet
```

```
Audit my IAM credentials — check root MFA, root access keys, and users without MFA
```

```
Is CloudTrail properly configured? Check for logging gaps
```

```
What are my top 5 AWS services by cost this month?
```

```
Find all EBS volumes that are unattached and estimate their monthly cost
```

```
Run all cost and security checks and summarize findings by severity
```

---

## Troubleshooting

**Server fails to start:**
```bash
# Test server manually
PYTHONPATH=src .venv/bin/python src/mcp_servers/security/server.py
```

**AWS credentials not found:**
```bash
export AWS_PROFILE=your-profile
# or
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
```

**Module not found error:**
```bash
make install   # reinstall deps into .venv
```

**Trusted Advisor returns empty:**
- Requires Business or Enterprise AWS support plan
- Returns `{"checks": [], "warning": "..."}` on Developer/free accounts — expected behavior

**GuardDuty / Security Hub returns warning:**
- Service not enabled in the region → enable in AWS console first
- Tools return gracefully with `warning` field, never raise exceptions

---

## Running a Specific Server Only

```bash
# Start just the security server for testing
PYTHONPATH=src .venv/bin/python src/mcp_servers/security/server.py

# Or with mcp dev (interactive inspector)
PYTHONPATH=src mcp dev src/mcp_servers/security/server.py
```

---

## Architecture Note

MCP servers are **thin wrappers** — all business logic lives in `src/agent/tools/`. The same functions run inside Lambda at production time and via MCP in this interactive mode. No logic duplication, no drift.

```
Claude Code CLI
      │
      │ MCP (stdio)
      ▼
src/mcp_servers/security/server.py    ← thin FastMCP wrapper
      │
      │ Python import
      ▼
src/agent/tools/security.py           ← business logic (boto3 calls)
      │
      │ boto3
      ▼
AWS APIs (GuardDuty, Config, IAM, etc.)
```
