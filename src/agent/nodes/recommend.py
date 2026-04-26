"""Recommend node — converts anomalies into validated Finding objects."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from agent.guardrails import Guardrails, GuardrailsConfig, GuardrailsViolationError
from agent.models.finding import Finding, Recommendation
from agent.state import AgentState
from common.bedrock_client import BedrockClient
from common.config import AgentConfig
from common.logger import get_logger
from notifications.dynamodb_writer import DynamoDBWriter

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _strip_code_fences(text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()


def _extract_anomalies_from_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Search message history for the anomaly payload stored by analyze_node.

    Args:
        messages: LangChain message list from state.

    Returns:
        List of anomaly dicts, or empty list if none found.
    """
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = str(msg.content)
        try:
            parsed = json.loads(content)
            if "anomalies_found" in parsed:
                return list(parsed["anomalies_found"])
        except (json.JSONDecodeError, TypeError):
            continue
    return []


async def recommend_node(state: AgentState, config: RunnableConfig) -> AgentState:  # noqa: ARG001
    """Generate validated Finding objects from confirmed anomalies.

    Reads the anomaly list stored by analyze_node from the message history,
    sends it to Bedrock via the recommend prompt, validates each returned
    item against the Finding Pydantic model, filters below the threshold,
    and builds a final Recommendation object.

    Args:
        state: Current graph state with message history containing anomalies.
        config: LangGraph runnable config (unused directly, required by interface).

    Returns:
        Updated AgentState with ``recommendation`` populated.
    """
    investigation_id: str = state["investigation_id"]
    log = logger.bind(investigation_id=investigation_id, node="recommend")

    agent_config = AgentConfig()

    anomalies = _extract_anomalies_from_messages(state.get("messages", []))
    if not anomalies:
        log.warning("recommend_node_no_anomalies")
        state["recommendation"] = Recommendation(
            findings=[],
            total_estimated_monthly_usd=0.0,
            summary="No cost anomalies above the threshold were detected in this investigation.",
            investigation_id=investigation_id,
        )
        return state

    client = BedrockClient(agent_config)
    guards = Guardrails(
        GuardrailsConfig(
            max_iterations=agent_config.max_iterations,
            max_tokens_per_investigation=agent_config.max_tokens_per_investigation,
            bedrock_cost_ceiling_usd=agent_config.bedrock_cost_ceiling_usd,
        )
    )

    anomalies_json = json.dumps(anomalies, indent=2, default=str)

    system_prompt = _load_prompt("system.md")
    recommend_template = _load_prompt("recommend.md")
    recommend_prompt = recommend_template.format(
        anomalies=anomalies_json,
        cost_threshold_usd=agent_config.cost_threshold_usd,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=recommend_prompt),
    ]

    bedrock_response = client.invoke(messages)

    state["guardrails"].record_llm_call(
        bedrock_response.input_tokens,
        bedrock_response.output_tokens,
    )

    raw_content: str = str(bedrock_response.message.content)
    cleaned = _strip_code_fences(raw_content)

    try:
        raw_findings: list[dict[str, Any]] = json.loads(cleaned)
        if not isinstance(raw_findings, list):
            raise ValueError("Expected a JSON array of findings")
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning(
            "recommend_node_json_parse_error",
            error=str(exc),
            raw_preview=raw_content[:200],
        )
        state["error"] = f"recommend node failed to parse JSON: {exc}"
        state["recommendation"] = Recommendation(
            findings=[],
            total_estimated_monthly_usd=0.0,
            summary="Recommendation generation failed due to a JSON parse error.",
            investigation_id=investigation_id,
        )
        return state

    validated_findings: list[Finding] = []
    for raw in raw_findings:
        try:
            finding = Finding.model_validate(raw)
            if finding.estimated_monthly_usd >= agent_config.cost_threshold_usd:
                validated_findings.append(finding)
            else:
                log.info(
                    "recommend_node_finding_below_threshold",
                    estimated_usd=finding.estimated_monthly_usd,
                    threshold=agent_config.cost_threshold_usd,
                )
        except ValidationError as exc:
            log.warning("recommend_node_finding_validation_error", error=str(exc))

    total_usd = sum(f.estimated_monthly_usd for f in validated_findings)

    # Build a summary prompt to get an executive summary from the LLM
    summary_lines = [
        f"- {f.title} (~${f.estimated_monthly_usd:.2f}/month)" for f in validated_findings
    ]
    if summary_lines:
        summary = (
            f"Investigation identified {len(validated_findings)} cost-waste finding(s) "
            f"with a total estimated monthly savings of ${total_usd:.2f} USD. "
            f"Top findings: {'; '.join(summary_lines[:3])}."
        )
    else:
        summary = "No actionable cost-waste findings above the threshold were identified."

    recommendation = Recommendation(
        findings=validated_findings,
        total_estimated_monthly_usd=total_usd,
        summary=summary,
        investigation_id=investigation_id,
    )
    state["recommendation"] = recommendation
    state["findings"] = validated_findings
    state["messages"] = list(state.get("messages", [])) + messages + [bedrock_response.message]

    log.info(
        "recommend_node_complete",
        findings_count=len(validated_findings),
        total_savings_usd=total_usd,
    )

    try:
        writer = DynamoDBWriter(agent_config)
        writer.write_investigation(
            investigation_id=investigation_id,
            recommendation=recommendation,
            guardrails_state=state["guardrails"],
        )
    except Exception as exc:  # noqa: BLE001
        log.error("recommend_node_persistence_failed", error=str(exc))

    try:
        guards.check_all(state["guardrails"])
    except GuardrailsViolationError as exc:
        log.warning("recommend_node_guardrail_violation", reason=exc.reason)

    return state
