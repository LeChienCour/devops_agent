"""Unit tests for per-model Bedrock pricing in guardrails cost estimation."""

from __future__ import annotations

import pytest

from agent.guardrails import GuardrailsState

_HAIKU_MODEL_ID = "anthropic.claude-haiku-4-5-20251001-v1:0"
_SONNET_MODEL_ID = "anthropic.claude-sonnet-4-5-20250929-v1:0"


class TestGuardrailsPricing:
    """Verify record_llm_call applies the pricing table matching the model ID."""

    def test_guardrails_haiku_model_uses_haiku_pricing(self) -> None:
        """Haiku model ID prices at $0.001/$0.005 per 1K tokens."""
        state = GuardrailsState(model_id=_HAIKU_MODEL_ID)

        state.record_llm_call(input_tokens=1000, output_tokens=1000)

        assert state.estimated_cost_usd == pytest.approx(0.001 + 0.005)

    def test_guardrails_sonnet_model_uses_sonnet_pricing(self) -> None:
        """Sonnet model ID prices at $0.003/$0.015 per 1K tokens."""
        state = GuardrailsState(model_id=_SONNET_MODEL_ID)

        state.record_llm_call(input_tokens=1000, output_tokens=1000)

        assert state.estimated_cost_usd == pytest.approx(0.003 + 0.015)

    def test_guardrails_unknown_model_falls_back_to_sonnet_pricing(self) -> None:
        """Unknown or empty model ID falls back to Sonnet pricing."""
        state = GuardrailsState(model_id="anthropic.claude-future-9-9-v1:0")

        state.record_llm_call(input_tokens=1000, output_tokens=1000)

        assert state.estimated_cost_usd == pytest.approx(0.003 + 0.015)
