# Investigation Planning Prompt

You are starting a new FinOps cost-waste investigation with ID `{investigation_id}`.

## Available Tools

{available_tools}

## Task

Produce a concise investigation plan that specifies:

1. Which tools to invoke and why.
2. The date range to analyse (default: previous full calendar month).
3. The order of tool calls (most informative first).

## Output Format

Respond with **only** a JSON object matching this schema — no prose before or
after:

```json
{{
  "investigation_plan": "brief one-sentence description of what this investigation will do",
  "tools_to_invoke": ["get_cost_by_service", "get_cost_anomalies"],
  "date_range": {{
    "start": "YYYY-MM-DD",
    "end": "YYYY-MM-DD"
  }},
  "reasoning": "explain why these tools were chosen and what cost patterns they will surface"
}}
```

### Rules

- `tools_to_invoke` must be a subset of the available tools listed above.
- `date_range.start` must be before `date_range.end`.
- Use the previous full calendar month as the default date range unless there is
  a specific reason to deviate.
- Keep `reasoning` under 100 words.
