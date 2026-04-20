"""Unit tests for all four LangGraph nodes.

All Bedrock and AWS calls are mocked; no network or IAM access required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from agent.guardrails import GuardrailsState
from agent.models.finding import Finding, Recommendation, Severity
from agent.nodes.analyze import analyze_node
from agent.nodes.gather import gather_node
from agent.nodes.plan import plan_node
from agent.nodes.recommend import recommend_node
from agent.state import AgentState
from common.bedrock_client import BedrockResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text())


def _make_state(**overrides: Any) -> AgentState:
    """Return a minimal valid AgentState with optional field overrides."""
    base: AgentState = AgentState(
        investigation_id="test-inv-001",
        trigger="on_demand",
        messages=[],
        plan=None,
        gathered_data=[],
        findings=[],
        recommendation=None,
        needs_more_data=False,
        guardrails=GuardrailsState(),
        error=None,
    )
    base.update(overrides)  # type: ignore[attr-defined]
    return base


def _make_bedrock_response(content: str, input_tokens: int = 100, output_tokens: int = 200) -> BedrockResponse:
    return BedrockResponse(
        message=AIMessage(content=content),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=42.0,
    )


# ---------------------------------------------------------------------------
# Plan node tests
# ---------------------------------------------------------------------------


class TestPlanNode:
    """Tests for agent.nodes.plan.plan_node."""

    @pytest.mark.asyncio
    async def test_plan_node_valid_response_returns_plan(self) -> None:
        """Happy path: Bedrock returns valid JSON plan; state["plan"] is set."""
        plan_data = _load_fixture("plan_response.json")

        mock_response = _make_bedrock_response(json.dumps(plan_data))

        with patch("agent.nodes.plan.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            state = _make_state()
            result = await plan_node(state, MagicMock())

        assert result["plan"] is not None
        assert result["plan"]["tools_to_invoke"] == ["get_cost_by_service"]
        assert result["plan"]["date_range"]["start"] == "2026-03-01"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_plan_node_valid_response_updates_guardrails(self) -> None:
        """Token counts are recorded in guardrails state after invocation."""
        plan_data = _load_fixture("plan_response.json")
        mock_response = _make_bedrock_response(json.dumps(plan_data), input_tokens=500, output_tokens=300)

        with patch("agent.nodes.plan.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            state = _make_state()
            result = await plan_node(state, MagicMock())

        assert result["guardrails"].total_input_tokens == 500
        assert result["guardrails"].total_output_tokens == 300

    @pytest.mark.asyncio
    async def test_plan_node_invalid_json_sets_error(self) -> None:
        """When Bedrock returns non-JSON text, state['error'] is set and plan is None."""
        mock_response = _make_bedrock_response("This is not valid JSON at all!")

        with patch("agent.nodes.plan.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            state = _make_state()
            result = await plan_node(state, MagicMock())

        assert result["error"] is not None
        assert "plan node failed to parse JSON" in result["error"]
        assert result["plan"] is None

    @pytest.mark.asyncio
    async def test_plan_node_strips_markdown_code_fences(self) -> None:
        """JSON wrapped in ```json ... ``` fences is correctly parsed."""
        plan_data = _load_fixture("plan_response.json")
        wrapped = f"```json\n{json.dumps(plan_data)}\n```"
        mock_response = _make_bedrock_response(wrapped)

        with patch("agent.nodes.plan.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            state = _make_state()
            result = await plan_node(state, MagicMock())

        assert result["plan"] is not None
        assert result["error"] is None


# ---------------------------------------------------------------------------
# Gather node tests
# ---------------------------------------------------------------------------


class TestGatherNode:
    """Tests for agent.nodes.gather.gather_node."""

    @pytest.mark.asyncio
    async def test_gather_node_cost_explorer_success_appends_data(self) -> None:
        """get_cost_by_service response is appended to gathered_data."""
        ce_response = _load_fixture("cost_explorer_response.json")
        plan = _load_fixture("plan_response.json")

        mock_fn = MagicMock(return_value=ce_response)
        fake_registry = {"get_cost_by_service": (MagicMock(), mock_fn)}

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            state = _make_state(plan=plan)
            result = await gather_node(state, MagicMock())

        assert len(result["gathered_data"]) == 1
        assert result["gathered_data"][0]["tool"] == "get_cost_by_service"
        assert result["gathered_data"][0]["data"] == ce_response

    @pytest.mark.asyncio
    async def test_gather_node_increments_iteration(self) -> None:
        """Iteration counter is incremented by 1 after each gather call."""
        ce_response = _load_fixture("cost_explorer_response.json")
        plan = _load_fixture("plan_response.json")

        mock_fn = MagicMock(return_value=ce_response)
        fake_registry = {"get_cost_by_service": (MagicMock(), mock_fn)}

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            state = _make_state(plan=plan)
            result = await gather_node(state, MagicMock())

        assert result["guardrails"].iterations == 1

    @pytest.mark.asyncio
    async def test_gather_node_guardrail_exceeded_stops_loop(self) -> None:
        """When max iterations is already reached, needs_more_data is forced False."""
        ce_response = _load_fixture("cost_explorer_response.json")
        plan = _load_fixture("plan_response.json")

        # Pre-fill iterations to trigger violation on check_all
        guardrails = GuardrailsState(iterations=5)

        mock_fn = MagicMock(return_value=ce_response)
        fake_registry = {"get_cost_by_service": (MagicMock(), mock_fn)}

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            state = _make_state(plan=plan, guardrails=guardrails, needs_more_data=True)
            result = await gather_node(state, MagicMock())

        assert result["needs_more_data"] is False

    @pytest.mark.asyncio
    async def test_gather_node_unwired_tool_is_skipped(self) -> None:
        """Tools not in TOOL_REGISTRY are skipped; no exception is raised."""
        plan = {
            "investigation_plan": "test",
            "tools_to_invoke": ["nonexistent_tool_xyz"],
            "date_range": {"start": "2026-03-01", "end": "2026-04-01"},
            "reasoning": "test",
        }

        # Empty registry — all tools unknown
        with patch("agent.nodes.gather.TOOL_REGISTRY", {}):
            state = _make_state(plan=plan)
            result = await gather_node(state, MagicMock())

        assert result["gathered_data"] == []

    @pytest.mark.asyncio
    async def test_gather_node_no_plan_sets_needs_more_data_false(self) -> None:
        """Missing plan causes early return with needs_more_data=False."""
        state = _make_state(plan=None, needs_more_data=True)
        result = await gather_node(state, MagicMock())

        assert result["needs_more_data"] is False


# ---------------------------------------------------------------------------
# Analyze node tests
# ---------------------------------------------------------------------------


class TestAnalyzeNode:
    """Tests for agent.nodes.analyze.analyze_node."""

    @pytest.mark.asyncio
    async def test_analyze_node_anomaly_detected_sets_needs_more_data_false(self) -> None:
        """Valid analyze response with needs_more_data=false sets flag correctly."""
        analyze_data = _load_fixture("analyze_response.json")
        mock_response = _make_bedrock_response(json.dumps(analyze_data))

        ce_response = _load_fixture("cost_explorer_response.json")
        gathered = [{"tool": "get_cost_by_service", "data": ce_response}]

        with patch("agent.nodes.analyze.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            state = _make_state(gathered_data=gathered)
            result = await analyze_node(state, MagicMock())

        assert result["needs_more_data"] is False

    @pytest.mark.asyncio
    async def test_analyze_node_needs_more_data_true_when_llm_says_so(self) -> None:
        """When LLM responds with needs_more_data=true, flag is propagated."""
        analysis = {
            "anomalies_found": [],
            "needs_more_data": True,
            "additional_tools_needed": ["get_cost_anomalies"],
            "reasoning": "Need anomaly data to confirm the pattern.",
        }
        mock_response = _make_bedrock_response(json.dumps(analysis))

        with patch("agent.nodes.analyze.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            state = _make_state()
            result = await analyze_node(state, MagicMock())

        assert result["needs_more_data"] is True

    @pytest.mark.asyncio
    async def test_analyze_node_anomalies_stored_in_messages(self) -> None:
        """Anomalies are stored as an AIMessage in state['messages']."""
        analyze_data = _load_fixture("analyze_response.json")
        mock_response = _make_bedrock_response(json.dumps(analyze_data))

        with patch("agent.nodes.analyze.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            state = _make_state()
            result = await analyze_node(state, MagicMock())

        ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert len(ai_messages) >= 1
        # The last AIMessage should contain the anomalies JSON
        last_ai_content = ai_messages[-1].content
        parsed = json.loads(str(last_ai_content))
        assert "anomalies_found" in parsed

    @pytest.mark.asyncio
    async def test_analyze_node_invalid_json_sets_error(self) -> None:
        """Non-JSON response sets error and forces needs_more_data=False."""
        mock_response = _make_bedrock_response("Sorry, I cannot analyse this data.")

        with patch("agent.nodes.analyze.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            state = _make_state()
            result = await analyze_node(state, MagicMock())

        assert result["error"] is not None
        assert result["needs_more_data"] is False

    @pytest.mark.asyncio
    async def test_analyze_node_guardrail_violation_forces_no_more_data(self) -> None:
        """GuardrailsViolation from check_all forces needs_more_data=False."""
        analysis = {
            "anomalies_found": [],
            "needs_more_data": True,
            "additional_tools_needed": ["get_cost_anomalies"],
            "reasoning": "Need more data.",
        }
        mock_response = _make_bedrock_response(json.dumps(analysis))

        # Token budget already exhausted
        guardrails = GuardrailsState(
            total_input_tokens=50_000,
            total_output_tokens=10_000,
        )

        with patch("agent.nodes.analyze.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            state = _make_state(guardrails=guardrails)
            result = await analyze_node(state, MagicMock())

        assert result["needs_more_data"] is False


# ---------------------------------------------------------------------------
# Recommend node tests
# ---------------------------------------------------------------------------

_VALID_FINDING_RAW: dict[str, Any] = {
    "finding_type": "nat_gateway_idle",
    "severity": "HIGH",
    "title": "Idle NAT Gateway generating $150/month",
    "description": "A NAT Gateway is incurring $150/month with no active workload.",
    "resource_id": None,
    "resource_arn": None,
    "estimated_monthly_usd": 150.0,
    "confidence": 0.87,
    "remediation_command": "aws ec2 delete-nat-gateway --nat-gateway-id nat-0abc123",
    "evidence": {"current_month_spend": 152.48},
}

_LOW_VALUE_FINDING_RAW: dict[str, Any] = {
    "finding_type": "s3_versioning_waste",
    "severity": "LOW",
    "title": "S3 versioning accumulating $2/month",
    "description": "Unused S3 version objects costing $2/month.",
    "resource_id": None,
    "resource_arn": None,
    "estimated_monthly_usd": 2.0,
    "confidence": 0.60,
    "remediation_command": None,
    "evidence": {},
}


def _state_with_anomalies(anomalies: list[dict[str, Any]]) -> AgentState:
    """Build state with an AIMessage containing the given anomaly list."""
    anomalies_message = AIMessage(content=json.dumps({"anomalies_found": anomalies}))
    return _make_state(messages=[anomalies_message])


class TestRecommendNode:
    """Tests for agent.nodes.recommend.recommend_node."""

    @pytest.mark.asyncio
    async def test_recommend_node_valid_findings_above_threshold(self) -> None:
        """High-value finding passes validation and appears in recommendation."""
        analyze_data = _load_fixture("analyze_response.json")
        mock_response = _make_bedrock_response(json.dumps([_VALID_FINDING_RAW]))

        state = _state_with_anomalies(analyze_data["anomalies_found"])

        with patch("agent.nodes.recommend.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = await recommend_node(state, MagicMock())

        rec = result["recommendation"]
        assert rec is not None
        assert len(rec.findings) == 1
        assert rec.findings[0].finding_type == "nat_gateway_idle"
        assert rec.findings[0].severity == Severity.HIGH
        assert rec.total_estimated_monthly_usd == 150.0

    @pytest.mark.asyncio
    async def test_recommend_node_filters_findings_below_threshold(self) -> None:
        """Finding with estimated_monthly_usd below cost_threshold is excluded."""
        mock_response = _make_bedrock_response(json.dumps([_LOW_VALUE_FINDING_RAW]))

        analyze_data = _load_fixture("analyze_response.json")
        state = _state_with_anomalies(analyze_data["anomalies_found"])

        with patch("agent.nodes.recommend.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = await recommend_node(state, MagicMock())

        rec = result["recommendation"]
        assert rec is not None
        # $2/month is below default $5 threshold
        assert len(rec.findings) == 0
        assert rec.total_estimated_monthly_usd == 0.0

    @pytest.mark.asyncio
    async def test_recommend_node_mixed_findings_filters_correctly(self) -> None:
        """Only findings above threshold appear; low-value ones are dropped."""
        both_findings = [_VALID_FINDING_RAW, _LOW_VALUE_FINDING_RAW]
        mock_response = _make_bedrock_response(json.dumps(both_findings))

        analyze_data = _load_fixture("analyze_response.json")
        state = _state_with_anomalies(analyze_data["anomalies_found"])

        with patch("agent.nodes.recommend.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = await recommend_node(state, MagicMock())

        rec = result["recommendation"]
        assert rec is not None
        assert len(rec.findings) == 1
        assert rec.findings[0].estimated_monthly_usd == 150.0

    @pytest.mark.asyncio
    async def test_recommend_node_no_anomalies_returns_empty_recommendation(self) -> None:
        """Empty message history produces an empty recommendation without LLM call."""
        state = _make_state()

        with patch("agent.nodes.recommend.BedrockClient") as mock_client_cls:
            result = await recommend_node(state, MagicMock())

        mock_client_cls.assert_not_called()
        rec = result["recommendation"]
        assert rec is not None
        assert rec.findings == []
        assert rec.total_estimated_monthly_usd == 0.0

    @pytest.mark.asyncio
    async def test_recommend_node_invalid_json_sets_error(self) -> None:
        """Non-JSON Bedrock response sets error and returns empty recommendation."""
        mock_response = _make_bedrock_response("I cannot generate recommendations.")

        analyze_data = _load_fixture("analyze_response.json")
        state = _state_with_anomalies(analyze_data["anomalies_found"])

        with patch("agent.nodes.recommend.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = await recommend_node(state, MagicMock())

        assert result["error"] is not None
        assert result["recommendation"] is not None
        assert result["recommendation"].findings == []

    @pytest.mark.asyncio
    async def test_recommend_node_guardrails_token_update(self) -> None:
        """Bedrock tokens are recorded in guardrails after recommend call."""
        mock_response = _make_bedrock_response(
            json.dumps([_VALID_FINDING_RAW]),
            input_tokens=400,
            output_tokens=600,
        )

        analyze_data = _load_fixture("analyze_response.json")
        state = _state_with_anomalies(analyze_data["anomalies_found"])

        with patch("agent.nodes.recommend.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = await recommend_node(state, MagicMock())

        assert result["guardrails"].total_input_tokens == 400
        assert result["guardrails"].total_output_tokens == 600

    @pytest.mark.asyncio
    async def test_recommend_node_finding_stored_in_state_findings(self) -> None:
        """Validated findings are also stored in state['findings'] list."""
        mock_response = _make_bedrock_response(json.dumps([_VALID_FINDING_RAW]))

        analyze_data = _load_fixture("analyze_response.json")
        state = _state_with_anomalies(analyze_data["anomalies_found"])

        with patch("agent.nodes.recommend.BedrockClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.invoke.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = await recommend_node(state, MagicMock())

        assert len(result["findings"]) == 1
        assert isinstance(result["findings"][0], Finding)
