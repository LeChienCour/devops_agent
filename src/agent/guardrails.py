"""Agent guardrails — enforced limits to prevent runaway loops and cost spikes."""

from __future__ import annotations

from dataclasses import dataclass, field

from aws_lambda_powertools import Logger

logger = Logger(service="finops-agent")

# Defaults — override via AgentConfig / environment
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_MAX_TOKENS_PER_INVESTIGATION = 50_000
DEFAULT_BEDROCK_COST_CEILING_USD = 0.50


@dataclass
class GuardrailsConfig:
    """Limits applied per investigation run."""

    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_tokens_per_investigation: int = DEFAULT_MAX_TOKENS_PER_INVESTIGATION
    bedrock_cost_ceiling_usd: float = DEFAULT_BEDROCK_COST_CEILING_USD


@dataclass
class GuardrailsState:
    """Mutable counters tracked during a single investigation run."""

    iterations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    violations: list[str] = field(default_factory=list)

    # Approximate Bedrock Claude Sonnet 4.5 pricing (us-east-1)
    # Update if pricing changes: https://aws.amazon.com/bedrock/pricing/
    _INPUT_COST_PER_1K = 0.003
    _OUTPUT_COST_PER_1K = 0.015

    def record_llm_call(self, input_tokens: int, output_tokens: int) -> None:
        """Update token counters and estimated cost after a Bedrock call."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.estimated_cost_usd += (input_tokens / 1000) * self._INPUT_COST_PER_1K
        self.estimated_cost_usd += (output_tokens / 1000) * self._OUTPUT_COST_PER_1K

    def increment_iteration(self) -> None:
        """Increment the gather→analyze loop counter."""
        self.iterations += 1


class GuardrailsViolation(Exception):
    """Raised when an investigation exceeds a configured guardrail limit."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Guardrail violated: {reason}")


class Guardrails:
    """Enforces iteration, token, and cost limits for an investigation run.

    Usage:
        guards = Guardrails(config)
        guards.check_iteration(state)       # call before each gather loop
        guards.check_tokens(state)          # call after each Bedrock response
        guards.check_cost(state)            # call after each Bedrock response
    """

    def __init__(self, config: GuardrailsConfig | None = None) -> None:
        self.config = config or GuardrailsConfig()

    def check_iteration(self, state: GuardrailsState) -> None:
        """Raise if the iteration limit has been reached.

        Args:
            state: Current run state.

        Raises:
            GuardrailsViolation: When iterations >= max_iterations.
        """
        if state.iterations >= self.config.max_iterations:
            msg = (
                f"Max iterations reached ({state.iterations}/{self.config.max_iterations}). "
                "Forcing recommend node."
            )
            logger.warning(msg)
            state.violations.append(msg)
            raise GuardrailsViolation(msg)

    def check_tokens(self, state: GuardrailsState) -> None:
        """Raise if the total token budget has been exceeded.

        Args:
            state: Current run state with updated token counts.

        Raises:
            GuardrailsViolation: When total tokens >= max_tokens_per_investigation.
        """
        total = state.total_input_tokens + state.total_output_tokens
        if total >= self.config.max_tokens_per_investigation:
            msg = (
                f"Token budget exhausted ({total}/{self.config.max_tokens_per_investigation}). "
                "Forcing recommend node."
            )
            logger.warning(msg)
            state.violations.append(msg)
            raise GuardrailsViolation(msg)

    def check_cost(self, state: GuardrailsState) -> None:
        """Raise if the estimated Bedrock cost ceiling has been exceeded.

        Args:
            state: Current run state with updated cost estimate.

        Raises:
            GuardrailsViolation: When estimated cost >= bedrock_cost_ceiling_usd.
        """
        if state.estimated_cost_usd >= self.config.bedrock_cost_ceiling_usd:
            msg = (
                f"Bedrock cost ceiling reached "
                f"(${state.estimated_cost_usd:.4f}/${self.config.bedrock_cost_ceiling_usd:.2f}). "
                "Forcing recommend node."
            )
            logger.warning(msg)
            state.violations.append(msg)
            raise GuardrailsViolation(msg)

    def check_all(self, state: GuardrailsState) -> None:
        """Run all guardrail checks in sequence.

        Args:
            state: Current run state.

        Raises:
            GuardrailsViolation: On first violated limit.
        """
        self.check_iteration(state)
        self.check_tokens(state)
        self.check_cost(state)
