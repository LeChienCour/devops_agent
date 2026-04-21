"""Pydantic v2 model for tracking investigation runs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class InvestigationStatus(StrEnum):
    """Lifecycle status of an investigation run."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Investigation(BaseModel):
    """Persistent record of a single agent investigation run.

    Attributes:
        investigation_id: Unique identifier, generated as UUID4.
        status: Current lifecycle status.
        trigger: What initiated the run — "scheduled" or "on_demand".
        started_at: UTC timestamp when the investigation began.
        completed_at: UTC timestamp when the investigation ended, or None if still running.
        findings_count: Number of findings that exceeded the cost threshold.
        total_savings_usd: Total estimated monthly savings across all findings.
        bedrock_cost_usd: Actual estimated Bedrock API cost for this investigation.
        guardrail_violations: List of guardrail violation messages recorded during the run.
        error: Error message if the investigation failed, otherwise None.
    """

    investigation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: InvestigationStatus
    trigger: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    findings_count: int = 0
    total_savings_usd: float = 0.0
    bedrock_cost_usd: float = 0.0
    guardrail_violations: list[str] = Field(default_factory=list)
    error: str | None = None
