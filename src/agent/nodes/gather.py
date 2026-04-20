"""Gather node — executes tools and appends raw responses to state."""

from __future__ import annotations

import inspect
from typing import Any

from langgraph.types import RunnableConfig

from agent.guardrails import Guardrails, GuardrailsConfig, GuardrailsViolation
from agent.state import AgentState
from agent.tools import TOOL_REGISTRY
from common.config import AgentConfig
from common.logger import get_logger

logger = get_logger(__name__)


async def gather_node(state: AgentState, config: RunnableConfig) -> AgentState:  # noqa: ARG001
    """Execute the tools listed in the plan and collect raw responses.

    Dispatches each tool listed in ``plan.tools_to_invoke`` via ``TOOL_REGISTRY``.
    Unknown tool names produce a warning log and are skipped without raising.

    Date parameters (``start_date`` / ``end_date``) are injected only for tools
    whose signatures declare them.  All tools receive the ``region`` kwarg from
    ``AgentConfig``.

    Increments the guardrails iteration counter and checks all guardrail limits
    after collection.  On ``GuardrailsViolation`` the loop is forced to stop by
    setting ``needs_more_data=False``.

    Args:
        state: Current graph state including the plan produced by plan_node.
        config: LangGraph runnable config (unused directly, required by interface).

    Returns:
        Updated AgentState with new data appended to ``gathered_data``.
    """
    investigation_id: str = state["investigation_id"]
    log = logger.bind(investigation_id=investigation_id, node="gather")

    plan: dict[str, Any] | None = state.get("plan")
    if not plan:
        log.warning("gather_node_no_plan")
        state["needs_more_data"] = False
        return state

    tools_to_invoke: list[str] = plan.get("tools_to_invoke", [])
    date_range: dict[str, str] = plan.get("date_range", {})
    start_date: str = date_range.get("start", "")
    end_date: str = date_range.get("end", "")

    agent_config = AgentConfig()
    guards = Guardrails(
        GuardrailsConfig(
            max_iterations=agent_config.max_iterations,
            max_tokens_per_investigation=agent_config.max_tokens_per_investigation,
            bedrock_cost_ceiling_usd=agent_config.bedrock_cost_ceiling_usd,
        )
    )

    gathered: list[dict[str, Any]] = list(state.get("gathered_data", []))

    for tool_name in tools_to_invoke:
        if tool_name not in TOOL_REGISTRY:
            log.warning("gather_node_tool_not_found", tool=tool_name)
            continue

        _, fn = TOOL_REGISTRY[tool_name]

        # Build kwargs dynamically from the function signature
        kwargs: dict[str, Any] = {"region": agent_config.aws_region}
        sig = inspect.signature(fn)
        if "start_date" in sig.parameters:
            if not start_date or not end_date:
                log.warning("gather_node_missing_dates", tool=tool_name)
                continue
            kwargs["start_date"] = start_date
        if "end_date" in sig.parameters:
            kwargs["end_date"] = end_date

        log.info("gather_node_invoking_tool", tool=tool_name)
        result = fn(**kwargs)
        gathered.append({"tool": tool_name, "data": result})
        log.info("gather_node_tool_complete", tool=tool_name)

    state["gathered_data"] = gathered

    # Increment after all tools in this round have run
    state["guardrails"].increment_iteration()

    try:
        guards.check_all(state["guardrails"])
    except GuardrailsViolation as exc:
        log.warning(
            "gather_node_guardrail_violation",
            reason=exc.reason,
        )
        state["needs_more_data"] = False

    return state
