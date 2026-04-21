"""Pydantic v2 models for FinOps findings and recommendations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """Finding severity levels ordered from most to least critical."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Finding(BaseModel):
    """A single cost-waste finding detected during an investigation.

    Attributes:
        finding_id: Unique identifier, generated automatically as UUID4.
        finding_type: Machine-readable type slug, e.g. "nat_gateway_idle".
        severity: Impact severity classification.
        title: Short human-readable title.
        description: Full description of the waste pattern.
        resource_id: AWS resource identifier (e.g. "i-0abc123"), if applicable.
        resource_arn: Full ARN of the affected resource, if applicable.
        estimated_monthly_usd: Estimated monthly waste in US dollars.
        confidence: LLM confidence score from 0.0 (uncertain) to 1.0 (certain).
        remediation_command: CLI command or IaC snippet to resolve the issue.
        evidence: Raw data that supports the finding.
        created_at: UTC timestamp when the finding was created.
    """

    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    finding_type: str
    severity: Severity
    title: str
    description: str
    resource_id: str | None = None
    resource_arn: str | None = None
    estimated_monthly_usd: float
    confidence: float = Field(ge=0.0, le=1.0)
    remediation_command: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Recommendation(BaseModel):
    """Aggregated output from a completed investigation.

    Attributes:
        findings: List of findings that exceed the cost threshold.
        total_estimated_monthly_usd: Sum of estimated monthly waste across all findings.
        summary: LLM-generated executive summary of findings and actions.
        investigation_id: ID of the investigation that produced this recommendation.
        created_at: UTC timestamp when the recommendation was created.
    """

    findings: list[Finding]
    total_estimated_monthly_usd: float
    summary: str
    investigation_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
