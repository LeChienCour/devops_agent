# Recommendation Generation Prompt

You are generating actionable FinOps findings from confirmed cost anomalies.

## Confirmed Anomalies

```json
{anomalies}
```

## Cost Threshold

Only produce findings whose `estimated_monthly_usd` exceeds **${cost_threshold_usd} USD**.

## Task

Convert each anomaly into a structured Finding with a concrete remediation
command and an executive-level summary.

## Output Format

Respond with **only** a JSON array of finding objects — no prose before or after:

```json
[
  {{
    "finding_type": "nat_gateway_idle",
    "severity": "HIGH",
    "title": "Idle NAT Gateway generating $150/month in data transfer costs",
    "description": "A NAT Gateway in us-east-1 is incurring $150/month in data transfer charges with no corresponding compute workload. The gateway appears to be processing traffic from a decommissioned application.",
    "resource_id": null,
    "resource_arn": null,
    "estimated_monthly_usd": 150.00,
    "confidence": 0.85,
    "remediation_command": "aws ec2 describe-nat-gateways --filter Name=state,Values=available | jq '.NatGateways[] | select(.Tags[].Value == \"unused\")'\n# After confirming the gateway is idle:\naws ec2 delete-nat-gateway --nat-gateway-id <nat-gateway-id>",
    "evidence": {{
      "current_month_spend": 150.00,
      "prior_month_spend": 12.00,
      "delta_pct": 1150
    }}
  }}
]
```

### Severity Mapping

| Range | Severity |
|-------|----------|
| > $200/month | CRITICAL |
| $50–$200/month | HIGH |
| $10–$50/month | MEDIUM |
| $5–$10/month | LOW |

### Rules

- `finding_type` must be a snake_case slug (e.g. `ebs_unattached`, `rds_rightsizing`).
- `severity` must be one of: CRITICAL, HIGH, MEDIUM, LOW.
- `confidence` must be between 0.0 and 1.0.
- `resource_id` and `resource_arn` must be `null` if not present in the evidence.
- `remediation_command` must be a copy-pasteable AWS CLI snippet or Terraform block.
- Omit any finding below ${cost_threshold_usd}/month.
- Return an empty array `[]` if no anomalies qualify.
