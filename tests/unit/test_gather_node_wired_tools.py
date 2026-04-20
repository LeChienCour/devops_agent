"""Unit tests for the refactored gather_node with dynamic TOOL_REGISTRY dispatch."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agent.guardrails import GuardrailsState
from agent.state import AgentState


def _make_state(**overrides: Any) -> AgentState:
    """Return a minimal valid AgentState with optional field overrides."""
    base: AgentState = AgentState(
        investigation_id="test-gather-001",
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


def _make_plan(tools: list[str]) -> dict[str, Any]:
    return {
        "investigation_plan": "test plan",
        "tools_to_invoke": tools,
        "date_range": {"start": "2026-03-01", "end": "2026-04-01"},
        "reasoning": "unit test",
    }


# ---------------------------------------------------------------------------
# test_gather_node_invokes_all_tools_in_plan
# ---------------------------------------------------------------------------


class TestGatherNodeInvokesTools:
    """Verify gather_node dispatches every tool listed in the plan."""

    @pytest.mark.asyncio
    async def test_gather_node_invokes_all_tools_in_plan(self) -> None:
        """All tool names in plan.tools_to_invoke produce a gathered_data entry."""
        fake_result_a = {"volumes": []}
        fake_result_b = {"eips": []}

        fake_fn_a = MagicMock(return_value=fake_result_a)
        fake_fn_b = MagicMock(return_value=fake_result_b)

        fake_registry = {
            "list_unattached_ebs_volumes": (MagicMock(), fake_fn_a),
            "list_unassociated_eips": (MagicMock(), fake_fn_b),
        }

        plan = _make_plan(["list_unattached_ebs_volumes", "list_unassociated_eips"])
        state = _make_state(plan=plan)

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            from agent.nodes.gather import gather_node

            result = await gather_node(state, MagicMock())

        assert len(result["gathered_data"]) == 2
        tool_names = {entry["tool"] for entry in result["gathered_data"]}
        assert tool_names == {"list_unattached_ebs_volumes", "list_unassociated_eips"}

    @pytest.mark.asyncio
    async def test_gather_node_data_matches_tool_return_value(self) -> None:
        """The data field in gathered_data matches the callable's return value."""
        fake_data = {"nat_gateways": [{"nat_gateway_id": "nat-abc", "is_idle": True}]}
        fake_fn = MagicMock(return_value=fake_data)

        fake_registry = {
            "list_idle_nat_gateways": (MagicMock(), fake_fn),
        }

        plan = _make_plan(["list_idle_nat_gateways"])
        state = _make_state(plan=plan)

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            from agent.nodes.gather import gather_node

            result = await gather_node(state, MagicMock())

        assert result["gathered_data"][0]["data"] == fake_data


# ---------------------------------------------------------------------------
# test_gather_node_skips_unknown_tool_with_warning
# ---------------------------------------------------------------------------


class TestGatherNodeSkipsUnknownTool:
    """Verify gather_node skips unknown tools without raising."""

    @pytest.mark.asyncio
    async def test_gather_node_skips_unknown_tool_with_warning(self) -> None:
        """Unknown tool name is silently skipped; gathered_data stays empty."""
        fake_registry: dict[str, Any] = {}  # empty registry — all tools unknown

        plan = _make_plan(["nonexistent_tool_xyz"])
        state = _make_state(plan=plan)

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            from agent.nodes.gather import gather_node

            result = await gather_node(state, MagicMock())

        assert result["gathered_data"] == []

    @pytest.mark.asyncio
    async def test_gather_node_partial_unknown_tools_skipped(self) -> None:
        """Known tools execute; unknown tools are silently skipped."""
        fake_fn = MagicMock(return_value={"log_groups": []})
        fake_registry = {
            "list_log_groups_without_retention": (MagicMock(), fake_fn),
        }

        plan = _make_plan(["list_log_groups_without_retention", "completely_unknown_tool"])
        state = _make_state(plan=plan)

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            from agent.nodes.gather import gather_node

            result = await gather_node(state, MagicMock())

        assert len(result["gathered_data"]) == 1
        assert result["gathered_data"][0]["tool"] == "list_log_groups_without_retention"


# ---------------------------------------------------------------------------
# test_gather_node_passes_region_to_all_tools
# ---------------------------------------------------------------------------


class TestGatherNodePassesRegion:
    """Verify gather_node forwards aws_region to every tool callable."""

    @pytest.mark.asyncio
    async def test_gather_node_passes_region_to_all_tools(self) -> None:
        """region kwarg matches AgentConfig.aws_region on every tool call."""
        fake_fn = MagicMock(return_value={"volumes": []})
        fake_registry = {
            "list_unattached_ebs_volumes": (MagicMock(), fake_fn),
        }

        plan = _make_plan(["list_unattached_ebs_volumes"])
        state = _make_state(plan=plan)

        with (
            patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry),
            patch("agent.nodes.gather.AgentConfig") as mock_config_cls,
        ):
            mock_config = MagicMock()
            mock_config.aws_region = "eu-west-1"
            mock_config.max_iterations = 5
            mock_config.max_tokens_per_investigation = 50_000
            mock_config.bedrock_cost_ceiling_usd = 0.50
            mock_config_cls.return_value = mock_config

            from agent.nodes.gather import gather_node

            await gather_node(state, MagicMock())

        call_kwargs = fake_fn.call_args.kwargs
        assert call_kwargs.get("region") == "eu-west-1"

    @pytest.mark.asyncio
    async def test_gather_node_passes_region_to_multiple_tools(self) -> None:
        """All tools in the plan receive the same region kwarg."""
        fn_a = MagicMock(return_value={"volumes": []})
        fn_b = MagicMock(return_value={"eips": []})
        fake_registry = {
            "list_unattached_ebs_volumes": (MagicMock(), fn_a),
            "list_unassociated_eips": (MagicMock(), fn_b),
        }

        plan = _make_plan(["list_unattached_ebs_volumes", "list_unassociated_eips"])
        state = _make_state(plan=plan)

        with (
            patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry),
            patch("agent.nodes.gather.AgentConfig") as mock_config_cls,
        ):
            mock_config = MagicMock()
            mock_config.aws_region = "ap-southeast-1"
            mock_config.max_iterations = 5
            mock_config.max_tokens_per_investigation = 50_000
            mock_config.bedrock_cost_ceiling_usd = 0.50
            mock_config_cls.return_value = mock_config

            from agent.nodes.gather import gather_node

            await gather_node(state, MagicMock())

        assert fn_a.call_args.kwargs.get("region") == "ap-southeast-1"
        assert fn_b.call_args.kwargs.get("region") == "ap-southeast-1"


# ---------------------------------------------------------------------------
# Guardrails integration
# ---------------------------------------------------------------------------


class TestGatherNodeGuardrails:
    """Verify guardrail behaviour is preserved after the registry refactor."""

    @pytest.mark.asyncio
    async def test_gather_node_increments_iteration(self) -> None:
        """Iteration counter increments by 1 per gather_node call."""
        fake_fn = MagicMock(return_value={"volumes": []})
        fake_registry = {
            "list_unattached_ebs_volumes": (MagicMock(), fake_fn),
        }

        plan = _make_plan(["list_unattached_ebs_volumes"])
        state = _make_state(plan=plan)

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            from agent.nodes.gather import gather_node

            result = await gather_node(state, MagicMock())

        assert result["guardrails"].iterations == 1

    @pytest.mark.asyncio
    async def test_gather_node_guardrail_exceeded_stops_loop(self) -> None:
        """Pre-filled iteration count triggers violation and sets needs_more_data=False."""
        fake_fn = MagicMock(return_value={"volumes": []})
        fake_registry = {
            "list_unattached_ebs_volumes": (MagicMock(), fake_fn),
        }

        plan = _make_plan(["list_unattached_ebs_volumes"])
        guardrails = GuardrailsState(iterations=5)
        state = _make_state(plan=plan, guardrails=guardrails, needs_more_data=True)

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            from agent.nodes.gather import gather_node

            result = await gather_node(state, MagicMock())

        assert result["needs_more_data"] is False

    @pytest.mark.asyncio
    async def test_gather_node_no_plan_returns_needs_more_data_false(self) -> None:
        """Missing plan causes early return with needs_more_data=False."""
        fake_registry: dict[str, Any] = {}
        state = _make_state(plan=None, needs_more_data=True)

        with patch("agent.nodes.gather.TOOL_REGISTRY", fake_registry):
            from agent.nodes.gather import gather_node

            result = await gather_node(state, MagicMock())

        assert result["needs_more_data"] is False
