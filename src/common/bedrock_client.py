"""Thin retry-wrapped client around langchain_aws.ChatBedrockConverse.

Security note (CLAUDE.md): full response content is never logged.
Only token counts, model ID, and latency are emitted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import ClientError
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import AIMessage, BaseMessage
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from common.config import AgentConfig
from common.logger import get_logger

logger = get_logger(__name__)

_RETRYABLE_CODES = frozenset(
    {
        "ThrottlingException",
        "ServiceUnavailableException",
        "ModelStreamErrorException",
        "ModelTimeoutException",
        "InternalServerException",
        "TooManyRequestsException",
    }
)


def _is_retryable(exc: BaseException) -> bool:
    """Return True when *exc* is a retryable Bedrock ClientError."""
    if not isinstance(exc, ClientError):
        return False
    code: str = exc.response.get("Error", {}).get("Code", "")
    return code in _RETRYABLE_CODES


@dataclass
class BedrockResponse:
    """Structured result from a single Bedrock invocation.

    Attributes:
        message: The AIMessage returned by ChatBedrockConverse.
        input_tokens: Number of tokens in the prompt.
        output_tokens: Number of tokens in the completion.
        latency_ms: Wall-clock latency for the call in milliseconds.
    """

    message: AIMessage
    input_tokens: int
    output_tokens: int
    latency_ms: float


class BedrockClient:
    """Wraps ChatBedrockConverse with retries, token tracking, and structured logging.

    Args:
        config: Runtime configuration containing model ID, region, etc.
    """

    def __init__(self, config: AgentConfig) -> None:
        self._model_id = config.bedrock_model_id
        self._region = config.aws_region
        self._llm = ChatBedrockConverse(
            model=config.bedrock_model_id,
            region_name=config.aws_region,
        )

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def invoke(
        self,
        messages: list[BaseMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> BedrockResponse:
        """Invoke the Bedrock model and return a structured response.

        Args:
            messages: LangChain message history to send to the model.
            tools: Optional list of tool schemas in Bedrock tool_use format.

        Returns:
            BedrockResponse with the AIMessage and token/latency metadata.

        Raises:
            ClientError: For non-retryable AWS errors after exhausting retries.
        """
        llm: ChatBedrockConverse = self._llm
        if tools:
            llm = self._llm.bind_tools(tools)  # type: ignore[assignment]

        start = time.monotonic()
        response: AIMessage = llm.invoke(messages)
        latency_ms = (time.monotonic() - start) * 1000

        usage: dict[str, Any] = getattr(response, "usage_metadata", {}) or {}
        input_tokens: int = int(usage.get("input_tokens", 0))
        output_tokens: int = int(usage.get("output_tokens", 0))

        logger.info(
            "bedrock_invocation",
            model_id=self._model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 2),
        )

        return BedrockResponse(
            message=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
