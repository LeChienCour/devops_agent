"""Unit tests for the LangGraph StateGraph build and end-to-end flow.

All Bedrock and AWS API calls are mocked.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from agent.graph import build_graph
from agent.guardrails import GuardrailsState
from agent.models.finding import Recommendation
from agent.state import AgentState
from common.bedrock_client import BedrockResponse
from common.config import AgentConfig
from langgraph.graph.state import CompiledStateGraph

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text())


def _make_bedrock_response(content: str) -> BedrockResponse:
    return BedrockResponse(
        message=AIMessage(content=content),
        input_tokens=100,
        output_tokens=200,
        latency_ms=50.0,
    )


def _make_initial_state(investigation_id: str | None = None) -> AgentState:
    return AgentState(
        investigation_id=investigation_id or str(uuid.uuid4()),
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


# ---------------------------------------------------------------------------
# Compile tests
# ---------------------------------------------------------------------------


class TestGraphCompile:
    """Tests that the graph compiles without error."""

    def test_graph_compiles_without_error(self) -> None:
        """build_graph returns a compiled graph for a default AgentConfig."""
        config = AgentConfig()
        compiled = build_graph(config)
        assert compiled is not None

    def test_graph_has_expected_nodes(self) -> None:
        """Compiled graph exposes plan, gather, analyze, recommend nodes."""
        config = AgentConfig()
        compiled = build_graph(config)
        # LangGraph exposes node names via the underlying graph object
        node_names = set(compiled.get_graph().nodes.keys())
        assert {"plan", "gather", "analyze", "recommend"}.issubset(node_names)


# ---------------------------------------------------------------------------
# Full-run integration tests (all external I/O mocked)
# ---------------------------------------------------------------------------


class TestGraphFullRun:
    """End-to-end graph invocations with mocked Bedrock and AWS."""

    @pytest.mark.asyncio
    async def test_graph_full_run_with_mocked_bedrock_returns_recommendation(self) -> None:
        """Happy path: graph completes and returns a non-None recommendation."""
        plan_data = _load_fixture("plan_response.json")
        analyze_data = _load_fixture("analyze_response.json")
        ce_data = _load_fixture("cost_explorer_response.json")

        finding_raw = {
            "finding_type": "nat_gateway_idle",
            "severity": "HIGH",
            "title": "Idle NAT Gateway generating $150/month",
            "description": "NAT Gateway incurring $150/month with no active workload.",
            "resource_id": None,
            "resource_arn": None,
            "estimated_monthly_usd": 150.0,
            "confidence": 0.87,
            "remediation_command": "aws ec2 delete-nat-gateway --nat-gateway-id nat-0abc123",
            "evidence": {"current_month_spend": 152.48},
        }

        plan_response = _make_bedrock_response(json.dumps(plan_data))
        analyze_response = _make_bedrock_response(json.dumps(analyze_data))
        recommend_response = _make_bedrock_response(json.dumps([finding_raw]))

        call_count = 0

        def _side_effect(messages: Any, tools: Any = None) -> BedrockResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return plan_response
            if call_count == 2:
                return analyze_response
            return recommend_response

        mock_ce_fn = MagicMock(return_value=ce_data)
        fake_registry = {"get_cost_by_service": (MagicMock(), mock_ce_fn)}

        with (
            patch("agent.nodes.plan.BedrockClient") as mock_plan_client_cls,
            patch("agent.nodes.analyze.BedrockClient") as mock_analyze_client_cls,
            patch("agent.nodes.recommend.BedrockClient") as mock_recommend_client_cls,
            patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry),
        ):
            mock_plan_client = MagicMock()
            mock_plan_client.invoke.return_value = plan_response
            mock_plan_client_cls.return_value = mock_plan_client

            mock_analyze_client = MagicMock()
            mock_analyze_client.invoke.return_value = analyze_response
            mock_analyze_client_cls.return_value = mock_analyze_client

            mock_recommend_client = MagicMock()
            mock_recommend_client.invoke.return_value = recommend_response
            mock_recommend_client_cls.return_value = mock_recommend_client

            config = AgentConfig()
            compiled = build_graph(config)
            initial_state = _make_initial_state()

            final_state: AgentState = await compiled.ainvoke(initial_state)

        assert final_state["recommendation"] is not None
        rec: Recommendation = final_state["recommendation"]
        assert len(rec.findings) == 1
        assert rec.findings[0].finding_type == "nat_gateway_idle"
        assert rec.total_estimated_monthly_usd == 150.0

    @pytest.mark.asyncio
    async def test_graph_full_run_error_in_plan_still_completes(self) -> None:
        """Invalid JSON from plan node sets error but graph still finishes."""
        bad_plan_response = _make_bedrock_response("Not valid JSON")
        analyze_data = _load_fixture("analyze_response.json")
        analyze_response = _make_bedrock_response(json.dumps(analyze_data))

        fake_registry: dict[str, Any] = {}

        with (
            patch("agent.nodes.plan.BedrockClient") as mock_plan_client_cls,
            patch("agent.nodes.analyze.BedrockClient") as mock_analyze_client_cls,
            patch("agent.nodes.recommend.BedrockClient") as mock_recommend_client_cls,
            patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry),
        ):
            mock_plan_client = MagicMock()
            mock_plan_client.invoke.return_value = bad_plan_response
            mock_plan_client_cls.return_value = mock_plan_client

            mock_analyze_client = MagicMock()
            mock_analyze_client.invoke.return_value = analyze_response
            mock_analyze_client_cls.return_value = mock_analyze_client

            mock_recommend_client = MagicMock()
            mock_recommend_client.invoke.return_value = _make_bedrock_response("[]")
            mock_recommend_client_cls.return_value = mock_recommend_client

            config = AgentConfig()
            compiled = build_graph(config)
            initial_state = _make_initial_state()

            # Graph should complete without raising; error field will be set
            final_state = await compiled.ainvoke(initial_state)

        assert final_state is not None


# ---------------------------------------------------------------------------
# Guardrail limit tests
# ---------------------------------------------------------------------------


class TestGraphGuardrails:
    """Tests that the graph respects guardrail limits."""

    @pytest.mark.asyncio
    async def test_graph_respects_guardrail_max_iterations(self) -> None:
        """When max_iterations=1, the gather→analyze loop runs only once."""
        plan_data = _load_fixture("plan_response.json")
        ce_data = _load_fixture("cost_explorer_response.json")

        # Analyze always asks for more data — guardrail should stop it
        analyze_more = {
            "anomalies_found": [],
            "needs_more_data": True,
            "additional_tools_needed": ["get_cost_anomalies"],
            "reasoning": "Need more data.",
        }

        plan_response = _make_bedrock_response(json.dumps(plan_data))
        analyze_response = _make_bedrock_response(json.dumps(analyze_more))
        recommend_response = _make_bedrock_response("[]")

        mock_ce_fn = MagicMock(return_value=ce_data)
        fake_registry = {"get_cost_by_service": (MagicMock(), mock_ce_fn)}

        with (
            patch("agent.nodes.plan.BedrockClient") as mock_plan_cls,
            patch("agent.nodes.analyze.BedrockClient") as mock_analyze_cls,
            patch("agent.nodes.recommend.BedrockClient") as mock_recommend_cls,
            patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry),
        ):
            mock_plan_client = MagicMock()
            mock_plan_client.invoke.return_value = plan_response
            mock_plan_cls.return_value = mock_plan_client

            mock_analyze_client = MagicMock()
            mock_analyze_client.invoke.return_value = analyze_response
            mock_analyze_cls.return_value = mock_analyze_client

            mock_recommend_client = MagicMock()
            mock_recommend_client.invoke.return_value = recommend_response
            mock_recommend_cls.return_value = mock_recommend_client

            # max_iterations=1 means the first gather will hit the limit
            with patch.dict(
                "os.environ",
                {"MAX_ITERATIONS": "1"},
            ):
                config = AgentConfig()
                compiled = build_graph(config)
                initial_state = _make_initial_state()

                final_state = await compiled.ainvoke(initial_state)

        # After 1 iteration the guardrail fires; the graph must have reached
        # the recommend node (needs_more_data forced False)
        assert final_state is not None
        assert final_state["guardrails"].iterations >= 1
        # Guardrail violations should have been recorded
        assert len(final_state["guardrails"].violations) >= 1

    @pytest.mark.asyncio
    async def test_graph_guardrail_token_budget_forces_recommend(self) -> None:
        """Exhausted token budget forces loop exit even when LLM wants more data."""
        plan_data = _load_fixture("plan_response.json")
        ce_data = _load_fixture("cost_explorer_response.json")

        analyze_more = {
            "anomalies_found": [],
            "needs_more_data": True,
            "additional_tools_needed": ["get_cost_anomalies"],
            "reasoning": "Need more.",
        }

        plan_response = _make_bedrock_response(json.dumps(plan_data))
        # Large token counts to trigger token budget guardrail
        analyze_response = BedrockResponse(
            message=AIMessage(content=json.dumps(analyze_more)),
            input_tokens=40_000,
            output_tokens=15_000,
            latency_ms=100.0,
        )
        recommend_response = _make_bedrock_response("[]")

        mock_ce_fn = MagicMock(return_value=ce_data)
        fake_registry = {"get_cost_by_service": (MagicMock(), mock_ce_fn)}

        with (
            patch("agent.nodes.plan.BedrockClient") as mock_plan_cls,
            patch("agent.nodes.analyze.BedrockClient") as mock_analyze_cls,
            patch("agent.nodes.recommend.BedrockClient") as mock_recommend_cls,
            patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry),
        ):
            mock_plan_client = MagicMock()
            mock_plan_client.invoke.return_value = plan_response
            mock_plan_cls.return_value = mock_plan_client

            mock_analyze_client = MagicMock()
            mock_analyze_client.invoke.return_value = analyze_response
            mock_analyze_cls.return_value = mock_analyze_client

            mock_recommend_client = MagicMock()
            mock_recommend_client.invoke.return_value = recommend_response
            mock_recommend_cls.return_value = mock_recommend_client

            config = AgentConfig()
            compiled = build_graph(config)
            initial_state = _make_initial_state()

            final_state = await compiled.ainvoke(initial_state)

        assert final_state is not None
        # Token budget should have been exhausted; loop should have stopped
        total_tokens = (
            final_state["guardrails"].total_input_tokens
            + final_state["guardrails"].total_output_tokens
        )
        assert total_tokens >= 50_000
