# FinOps Approaches — Comparison Table

> Comparing three approaches to AWS cost waste detection for teams that can't afford a dedicated FinOps engineer.

---

## TL;DR

| | Manual / DIY | AWS Managed Tools | FinOps Agent (this project) |
|---|---|---|---|
| Setup time | Hours–days | Minutes | ~30 min |
| Cost/month | Engineering time | $0–50+ | ~$1–3 |
| Finds new leak types | Only if you script it | Fixed catalog | Yes (LLM reasoning) |
| Explains WHY | No | Partially | Yes |
| Remediations | You write them | Generic docs | Exact commands |
| Slack integration | DIY | Limited | Built-in Block Kit |
| Historical record | You build it | Cost Explorer | DynamoDB (90d) |
| CI shift-left | You add it | No | Infracost in pipeline |

---

## Detailed Comparison

### 1. Manual / DIY Scripts

**What teams actually do:**
- Write one-off boto3 scripts when someone notices a high bill
- CloudWatch dashboard with cost anomaly alerts
- Monthly spreadsheet review of Cost Explorer

**Pros:**
- Full control
- No dependency on third-party tools
- Can be very specific to team's infrastructure

**Cons:**
- Doesn't scale — every new leak type requires a new script
- No LLM reasoning — can't explain *why* something is waste
- Remediations are generic or missing entirely
- Alert fatigue: thresholds tuned manually, not contextually
- Knowledge lives in one person's head

**Typical monthly cost:**  
~2–4 hours of senior engineer time = $200–600 in labor.  
Plus whatever leaks persist between reviews.

---

### 2. AWS Native Tools

#### AWS Cost Anomaly Detection

- ML-based anomaly detection on Cost Explorer data
- Sends SNS alerts when spend deviates from baseline
- **Does not** explain root cause or suggest remediation
- Free for the detection; standard Cost Explorer costs apply

#### AWS Trusted Advisor

- Covers ~5 FinOps checks (idle EBS, unassociated EIPs, underutilized EC2, etc.)
- Fixed catalog — doesn't adapt to new patterns
- Business/Enterprise Support plan required for full checks (~$100–15,000/month)
- No Slack integration out of the box
- No per-finding dollar impact calculation

#### Amazon DevOps Guru

- ML ops recommendations for performance and availability
- Limited FinOps coverage (not the primary use case)
- ~$0.0028/resource/hour for continuous profiling
- For 100 resources: ~$200/month

#### AWS Compute Optimizer

- Rightsizing for EC2, Lambda, EBS, ECS, Auto Scaling
- Solid for compute — does not cover networking waste (EIPs, NAT) or storage (orphaned snapshots)
- Free (basic), Enhanced Infrastructure Metrics costs extra

**Combined gap:** AWS tools cover *some* dimensions well but don't unify findings, explain root causes contextually, or integrate into your chat workflow with actionable per-resource remediations.

---

### 3. FinOps Agent (This Project)

**Architecture:** LangGraph StateGraph on Lambda + Amazon Bedrock (Claude Sonnet) + DynamoDB + Slack Block Kit

**What makes it different:**

#### Reasoning, not just detection
The LLM doesn't just flag a resource — it reasons about *why* it's waste, considers context (age, tags, account patterns), and generates a remediation that fits the specific resource ID.

```
Finding: EBS volume vol-0abc123 (50 GB gp2, us-east-1a)
Unattached for 47 days. No snapshots in last 30 days.
Estimated monthly waste: $5.00
Remediation: aws ec2 delete-volume --volume-id vol-0abc123
```

#### Adaptive investigation loop
The agent plans which tools to call, executes them, and if findings are ambiguous it iterates — requesting more data before committing to a finding. Static scripts can't do this.

#### 8 leak categories in one run
NAT Gateway idle · EBS unattached · EBS gp2→gp3 · EIP unassociated · Orphaned snapshots · Lambda oversized · Log Groups without retention · Stopped EC2 with EBS

#### Shift-left with Infracost
Infracost runs on every PR that touches `infra/`, posts a cost delta comment before the resource is created. The agent catches what slips through to production.

#### Cost of the agent itself
~$1–3/month (Bedrock: 4 runs/week × ~$0.30 each). The agent pays for itself if it catches one unattached EBS volume per month.

---

## Cost Comparison — 100-Resource AWS Account

| Approach | Setup | Monthly cost | Annual savings potential |
|---|---|---|---|
| No FinOps tooling | $0 | $0 | $0 (leaks persist) |
| Manual scripts (4h/month) | 8h | ~$400 labor | Depends on discipline |
| Trusted Advisor (Business) | 15 min | ~$100+ support | Partial coverage |
| DevOps Guru (100 resources) | 30 min | ~$200 | Ops-focused, not FinOps |
| Cost Anomaly Detection | 15 min | ~$5 | Alerts only, no remediation |
| **FinOps Agent** | **30 min** | **~$1–3** | **$50–500+ per account** |

---

## When NOT to Use This Agent

- **Regulated environments** where LLM-generated recommendations can't be acted on without human review → add an approval step before remediations
- **Very large accounts (1000+ resources)** → need pagination tuning and parallel investigation runs; current guardrails assume <200 relevant resources per run
- **Multi-account organizations** → currently single-account; would need AWS Organizations integration for fleet-wide coverage

---

## References

- [AWS Cost Anomaly Detection pricing](https://aws.amazon.com/aws-cost-management/aws-cost-anomaly-detection/pricing/)
- [AWS Trusted Advisor checks list](https://docs.aws.amazon.com/awssupport/latest/user/trusted-advisor-check-reference.html)
- [Amazon DevOps Guru pricing](https://aws.amazon.com/devops-guru/pricing/)
- [Infracost — open source Terraform cost estimation](https://www.infracost.io/)
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/)
- [Amazon Bedrock — Claude model pricing](https://aws.amazon.com/bedrock/pricing/)
