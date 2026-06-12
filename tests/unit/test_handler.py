"""Unit tests for the Lambda handler event parsing."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from agent import handler

_HAIKU_MODEL_ID = "anthropic.claude-haiku-4-5-20251001-v1:0"


def _make_final_state(initial_state: dict[str, Any]) -> dict[str, Any]:
    final = dict(initial_state)
    final["recommendation"] = None
    return final


def _invoke_handler(event: dict[str, Any]) -> dict[str, Any]:
    """Run lambda_handler with graph and metrics mocked; return the initial state."""
    captured: dict[str, Any] = {}

    async def _fake_ainvoke(state: dict[str, Any]) -> dict[str, Any]:
        captured.update(state)
        return _make_final_state(state)

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=_fake_ainvoke)

    with (
        patch.object(handler, "_GRAPH", mock_graph),
        patch.object(handler, "MetricsPublisher") as mock_metrics,
    ):
        mock_metrics.return_value.record_investigation = MagicMock()
        handler.lambda_handler(event, MagicMock())

    return captured


class TestHandlerModelOverride:
    """Verify per-invocation model_id override reaches the agent state."""

    def test_handler_event_model_id_overrides_config(self) -> None:
        """Top-level model_id lands in state and guardrails pricing context."""
        state = _invoke_handler({"model_id": _HAIKU_MODEL_ID})

        assert state["model_id"] == _HAIKU_MODEL_ID
        assert state["guardrails"].model_id == _HAIKU_MODEL_ID

    def test_handler_event_detail_model_id_overrides_config(self) -> None:
        """EventBridge-style detail.model_id is also honoured."""
        state = _invoke_handler({"detail": {"model_id": _HAIKU_MODEL_ID}})

        assert state["model_id"] == _HAIKU_MODEL_ID

    def test_handler_event_without_model_id_defaults_to_config(self) -> None:
        """No override: state model_id is None and guardrails use the config model."""
        state = _invoke_handler({})

        assert state["model_id"] is None
        assert state["guardrails"].model_id == handler._AGENT_CONFIG.bedrock_model_id

    def test_handler_event_detail_trigger_parses_trigger(self) -> None:
        """EventBridge nested detail.trigger is parsed instead of falling back."""
        state = _invoke_handler({"detail": {"trigger": "weekly-schedule"}})

        assert state["trigger"] == "weekly-schedule"
