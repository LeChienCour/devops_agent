"""LangGraph TypedDict state definition for the FinOps agent."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.graph import END as _END  # noqa: F401 — re-exported for graph module
from typing_extensions import TypedDict

from agent.guardrails import GuardrailsState
from agent.models.finding import Finding, Recommendation

__all__ = ["AgentState"]


class AgentState(TypedDict):
    """Full mutable state carried through the LangGraph StateGraph.

    Attributes:
        investigation_id: UUID4 string identifying this run.
        trigger: Source of the investigation — "scheduled" or "on_demand".
        messages: LangChain message history for the Bedrock conversation.
        plan: Structured plan produced by the plan node; None until set.
        gathered_data: Raw tool responses accumulated by gather nodes.
        findings: Validated Finding objects produced by the recommend node.
        recommendation: Final Recommendation object; None until recommend node runs.
        needs_more_data: When True the graph loops back to gather; set by analyze node.
        guardrails: Mutable counters and violation log enforced across nodes.
        error: Set to a non-None string when a node encounters an unrecoverable error.
    """

    investigation_id: str
    trigger: str
    messages: list[BaseMessage]
    plan: dict[str, Any] | None
    gathered_data: list[dict[str, Any]]
    findings: list[Finding]
    recommendation: Recommendation | None
    needs_more_data: bool
    guardrails: GuardrailsState
    error: str | None
