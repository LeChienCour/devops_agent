"""Analyze node — asks Bedrock to identify anomalies in gathered cost data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import RunnableConfig

from agent.guardrails import Guardrails, GuardrailsConfig, GuardrailsViolationError
from agent.state import AgentState
from common.bedrock_client import BedrockClient
from common.config import AgentConfig
from common.logger import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _strip_code_fences(text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()


async def analyze_node(state: AgentState, config: RunnableConfig) -> AgentState:  # noqa: ARG001
    """Invoke Bedrock to detect anomalies in the gathered cost data.

    Builds the analyze prompt, calls Bedrock, and extracts the
    ``needs_more_data`` flag and ``anomalies_found`` list from the response.
    Stores the raw anomaly JSON as an AIMessage so the recommend node can
    access it without re-parsing state.

    Runs guardrail checks after the LLM call; on ``GuardrailsViolationError`` forces
    ``needs_more_data=False`` to break the loop.

    Args:
        state: Current graph state with populated ``gathered_data``.
        config: LangGraph runnable config (unused directly, required by interface).

    Returns:
        Updated AgentState with ``needs_more_data`` and appended messages.
    """
    investigation_id: str = state["investigation_id"]
    log = logger.bind(investigation_id=investigation_id, node="analyze")

    agent_config = AgentConfig()
    client = BedrockClient(agent_config)
    guards = Guardrails(
        GuardrailsConfig(
            max_iterations=agent_config.max_iterations,
            max_tokens_per_investigation=agent_config.max_tokens_per_investigation,
            bedrock_cost_ceiling_usd=agent_config.bedrock_cost_ceiling_usd,
        )
    )

    gathered_data: list[dict[str, Any]] = state.get("gathered_data", [])
    gathered_json = json.dumps(gathered_data, indent=2, default=str)

    system_prompt = _load_prompt("system.md")
    analyze_template = _load_prompt("analyze.md")
    analyze_prompt = analyze_template.format(
        gathered_data=gathered_json,
        cost_threshold_usd=agent_config.cost_threshold_usd,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=analyze_prompt),
    ]

    bedrock_response = client.invoke(messages)

    state["guardrails"].record_llm_call(
        bedrock_response.input_tokens,
        bedrock_response.output_tokens,
    )

    raw_content: str = str(bedrock_response.message.content)
    cleaned = _strip_code_fences(raw_content)

    try:
        analysis: dict[str, Any] = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning(
            "analyze_node_json_parse_error",
            error=str(exc),
            raw_preview=raw_content[:200],
        )
        state["error"] = f"analyze node failed to parse JSON: {exc}"
        state["needs_more_data"] = False
        return state

    needs_more_data: bool = bool(analysis.get("needs_more_data", False))
    anomalies: list[Any] = analysis.get("anomalies_found", [])

    log.info(
        "analyze_node_complete",
        anomalies_count=len(anomalies),
        needs_more_data=needs_more_data,
        reasoning=analysis.get("reasoning", "")[:120],
    )

    # Persist anomalies as an AIMessage so the recommend node can read them
    anomalies_message = AIMessage(content=json.dumps({"anomalies_found": anomalies}))
    state["messages"] = list(state.get("messages", [])) + messages + [anomalies_message]
    state["needs_more_data"] = needs_more_data

    try:
        guards.check_all(state["guardrails"])
    except GuardrailsViolationError as exc:
        log.warning(
            "analyze_node_guardrail_violation",
            reason=exc.reason,
        )
        state["needs_more_data"] = False

    return state
