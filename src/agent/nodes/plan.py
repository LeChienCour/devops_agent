"""Plan node — asks Bedrock for a structured investigation plan."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import RunnableConfig

from agent.state import AgentState
from agent.tools.cost_explorer import TOOLS
from common.bedrock_client import BedrockClient
from common.config import AgentConfig
from common.logger import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Read a prompt file from the prompts directory.

    Args:
        filename: Filename relative to the prompts directory.

    Returns:
        File contents as a string.
    """
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences that the LLM sometimes wraps JSON in.

    Args:
        text: Raw LLM output string.

    Returns:
        String with leading/trailing code fences removed.
    """
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()


def _build_tool_list(tools: list[dict[str, Any]]) -> str:
    """Format the TOOLS list into a readable string for the prompt.

    Args:
        tools: List of Bedrock tool schema dicts.

    Returns:
        Newline-separated tool descriptions.
    """
    lines: list[str] = []
    for tool in tools:
        lines.append(f"- **{tool['name']}**: {tool['description']}")
    return "\n".join(lines)


async def plan_node(state: AgentState, config: RunnableConfig) -> AgentState:  # noqa: ARG001
    """Invoke Bedrock to produce a structured investigation plan.

    Loads system.md and plan.md, sends them to Bedrock, and stores the
    parsed JSON plan in ``state["plan"]``.

    Args:
        state: Current graph state.
        config: LangGraph runnable config (unused directly, required by interface).

    Returns:
        Updated AgentState with ``plan`` populated, or ``error`` set on failure.
    """
    investigation_id: str = state["investigation_id"]
    log = logger.bind(investigation_id=investigation_id, node="plan")

    agent_config = AgentConfig()
    client = BedrockClient(agent_config)

    system_prompt = _load_prompt("system.md")
    plan_template = _load_prompt("plan.md")

    available_tools = _build_tool_list(TOOLS)
    plan_prompt = plan_template.format(
        investigation_id=investigation_id,
        available_tools=available_tools,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=plan_prompt),
    ]

    bedrock_response = client.invoke(messages)

    state["guardrails"].record_llm_call(
        bedrock_response.input_tokens,
        bedrock_response.output_tokens,
    )

    raw_content: str = str(bedrock_response.message.content)
    cleaned = _strip_code_fences(raw_content)

    try:
        plan: dict[str, Any] = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning(
            "plan_node_json_parse_error",
            error=str(exc),
            raw_preview=raw_content[:200],
        )
        state["error"] = f"plan node failed to parse JSON: {exc}"
        return state

    state["plan"] = plan
    state["messages"] = list(state.get("messages", [])) + messages + [bedrock_response.message]

    log.info(
        "plan_node_complete",
        plan_summary=plan.get("investigation_plan", ""),
        tools=plan.get("tools_to_invoke", []),
    )

    return state
