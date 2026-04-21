# Cost Data Analysis Prompt

You are analysing raw AWS cost data collected by the FinOps agent tools.

## Gathered Data

```json
{gathered_data}
```

## Cost Threshold

Only flag anomalies whose estimated monthly impact exceeds **${cost_threshold_usd} USD**.

## Task

Examine the gathered data and identify cost-waste patterns, unexpected spikes, or
idle resources. For each candidate anomaly, assess whether additional data is
needed before a confident finding can be made.

## Output Format

Respond with **only** a JSON object matching this schema — no prose before or
after:

```json
{{
  "anomalies_found": [
    {{
      "service": "Amazon EC2",
      "pattern": "nat_gateway_idle",
      "estimated_monthly_usd": 150.00,
      "confidence": 0.85,
      "evidence": {{
        "current_month_spend": 150.00,
        "prior_month_spend": 12.00,
        "delta_pct": 1150
      }},
      "notes": "NAT Gateway data transfer cost spiked 1150% vs prior month with no corresponding EC2 increase"
    }}
  ],
  "needs_more_data": false,
  "additional_tools_needed": [],
  "reasoning": "brief explanation of findings and whether more data collection is warranted"
}}
```

### Rules

- Set `needs_more_data` to `true` only if a specific additional tool call would
  materially improve confidence in a finding already above the threshold.
- `additional_tools_needed` must be empty when `needs_more_data` is `false`.
- List only tool names from the available set: `get_cost_by_service`,
  `get_cost_anomalies`, `get_cost_forecast`.
- Keep `reasoning` under 150 words.
- Omit services with costs below ${cost_threshold_usd}/month from `anomalies_found`.
