"""Gather node — executes tools and appends raw responses to state."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from langchain_core.runnables import RunnableConfig

from agent.guardrails import Guardrails, GuardrailsConfig, GuardrailsViolationError
from agent.state import AgentState
from agent.tools import TOOL_REGISTRY
from common.config import get_config
from common.logger import get_logger

logger = get_logger(__name__)


def _build_tool_kwargs(
    fn: Any,
    start_date: str,
    end_date: str,
    region: str,
    tool_name: str,
    log: Any,
) -> dict[str, Any] | None:
    """Build the kwargs dict for a tool call, or return None to skip the tool."""
    kwargs: dict[str, Any] = {"region": region}
    sig = inspect.signature(fn)
    if "start_date" in sig.parameters:
        if not start_date or not end_date:
            log.warning("gather_node_missing_dates", tool=tool_name)
            return None
        kwargs["start_date"] = start_date
    if "end_date" in sig.parameters:
        kwargs["end_date"] = end_date
    return kwargs


async def _invoke_tool(tool_name: str, fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Run a sync tool in a thread and return the structured result."""
    result = await asyncio.to_thread(fn, **kwargs)
    return {"tool": tool_name, "data": result}


async def gather_node(state: AgentState, config: RunnableConfig) -> AgentState:  # noqa: ARG001
    """Execute the tools listed in the plan and collect raw responses.

    Dispatches each tool listed in ``plan.tools_to_invoke`` via ``TOOL_REGISTRY``
    in parallel using ``asyncio.gather``.  Unknown tool names produce a warning
    log and are skipped without raising.  A per-tool error is logged and the
    tool skipped when its invocation raises an exception; other tools still run.

    Date parameters (``start_date`` / ``end_date``) are injected only for tools
    whose signatures declare them.  All tools receive the ``region`` kwarg from
    ``get_config()``.

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

    agent_config = get_config()
    guards = Guardrails(
        GuardrailsConfig(
            max_iterations=agent_config.max_iterations,
            max_tokens_per_investigation=agent_config.max_tokens_per_investigation,
            bedrock_cost_ceiling_usd=agent_config.bedrock_cost_ceiling_usd,
        )
    )

    # Build coroutines for all valid tools
    tasks: list[Any] = []
    task_names: list[str] = []
    for tool_name in tools_to_invoke:
        if tool_name not in TOOL_REGISTRY:
            log.warning("gather_node_tool_not_found", tool=tool_name)
            continue

        _, fn = TOOL_REGISTRY[tool_name]
        kwargs = _build_tool_kwargs(
            fn, start_date, end_date, agent_config.aws_region, tool_name, log
        )
        if kwargs is None:
            continue

        log.info("gather_node_invoking_tool", tool=tool_name)
        tasks.append(_invoke_tool(tool_name, fn, kwargs))
        task_names.append(tool_name)

    gathered: list[dict[str, Any]] = list(state.get("gathered_data", []))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for tool_name, res in zip(task_names, results, strict=True):
            if isinstance(res, BaseException):
                log.warning("gather_node_tool_error", tool=tool_name, error=str(res))
            else:
                gathered.append(res)
                log.info("gather_node_tool_complete", tool=tool_name)

    state["gathered_data"] = gathered

    # Increment after all tools in this round have run
    state["guardrails"].increment_iteration()

    try:
        guards.check_all(state["guardrails"])
    except GuardrailsViolationError as exc:
        log.warning(
            "gather_node_guardrail_violation",
            reason=exc.reason,
        )
        state["needs_more_data"] = False

    return state
