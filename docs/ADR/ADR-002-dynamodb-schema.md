# ADR-002: DynamoDB Key Design

**Status:** Accepted  
**Date:** 2026-04-20  
**Deciders:** Diego Sandoval

---

## Context

PLAN.md §5 Phase 1 proposed schema `{investigation_id, timestamp, finding_type, status, data}` — insufficient for Phase 5 reporting queries (e.g., "all NAT Gateway findings over time") and for separating investigation metadata from individual findings.

## Decision

### Key design

| Attribute | Type | Description |
|-----------|------|-------------|
| `PK` | String | `investigation_id` (UUID) |
| `SK` | String | `finding#<ulid>` for findings; `meta#summary` for the run summary |
| `finding_type` | String | e.g. `nat_gateway_idle`, `ebs_unattached` |
| `severity` | String | `critical`, `high`, `medium`, `low` |
| `estimated_monthly_usd` | Number | Impact estimate |
| `status` | String | `open`, `acknowledged`, `resolved` |
| `data` | Map | Raw finding payload (Pydantic model serialized) |
| `created_at` | String | ISO-8601 timestamp |
| `ttl` | Number | Unix epoch — auto-expire demo data after 90 days |

### GSI

**GSI-1:** `finding_type` (PK) + `created_at` (SK)  
Purpose: "Show all findings of type X across all investigations over time" — needed for Phase 5 reports and trend detection.

## Consequences

- **Positive:** Single-table design; no joins; DynamoDB free tier covers demo volume.
- **Positive:** TTL prevents unbounded growth on demo account.
- **Negative:** Two item types (finding + meta) in one table require careful query discipline — always filter by SK prefix.
- **Migration note:** This schema must be in Terraform from Phase 1; DynamoDB schema changes are costly post-deployment.
