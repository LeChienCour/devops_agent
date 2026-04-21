#!/usr/bin/env python3
"""Run the FinOps agent locally for development and testing.

Usage::

    python scripts/run_local.py [--trigger on_demand]

Requires a ``.env`` file at the repository root with at minimum::

    AWS_REGION=us-east-1
    BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-5-20250929-v1:0
    DYNAMODB_TABLE_NAME=finops-agent-findings
    SNS_TOPIC_ARN=arn:aws:sns:us-east-1:000000000000:finops-alerts
    IS_LOCAL=true
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# Ensure the src directory is on the path when running as a script
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402 — must come after sys.path manipulation

load_dotenv(_REPO_ROOT / ".env")

from agent.graph import build_graph  # noqa: E402
from agent.guardrails import GuardrailsState  # noqa: E402
from agent.state import AgentState  # noqa: E402
from common.config import AgentConfig  # noqa: E402
from common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FinOps agent locally")
    parser.add_argument(
        "--trigger",
        default="on_demand",
        choices=["scheduled", "on_demand"],
        help="Investigation trigger source (default: on_demand)",
    )
    return parser.parse_args()


async def main(trigger: str = "on_demand") -> int:
    """Build and run the agent graph, pretty-printing findings to stdout.

    Args:
        trigger: Investigation trigger source.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    investigation_id = str(uuid.uuid4())
    log = logger.bind(investigation_id=investigation_id, trigger=trigger)
    log.info("local_run_started")

    try:
        agent_config = AgentConfig()
        graph = build_graph(agent_config)

        initial_state = AgentState(
            investigation_id=investigation_id,
            trigger=trigger,
            messages=[],
            plan=None,
            gathered_data=[],
            findings=[],
            recommendation=None,
            needs_more_data=False,
            guardrails=GuardrailsState(),
            error=None,
        )

        final_state: AgentState = await asyncio.wait_for(
            graph.ainvoke(initial_state),
            timeout=agent_config.investigation_timeout_sec,
        )

        recommendation = final_state.get("recommendation")
        guardrails = final_state["guardrails"]
        error = final_state.get("error")

        if error:
            print(f"\n[ERROR] {error}", file=sys.stderr)

        print("\n" + "=" * 70)
        print("FINOPS INVESTIGATION RESULTS")
        print("=" * 70)
        print(f"Investigation ID : {investigation_id}")
        print(f"Trigger          : {trigger}")
        print(f"Iterations       : {guardrails.iterations}")
        print(f"Bedrock Cost     : ${guardrails.estimated_cost_usd:.4f} USD")
        if guardrails.violations:
            print(f"Guardrail Alerts : {len(guardrails.violations)}")
            for v in guardrails.violations:
                print(f"  - {v}")

        if recommendation:
            print(f"\nFindings         : {len(recommendation.findings)}")
            print(f"Total Savings    : ${recommendation.total_estimated_monthly_usd:.2f}/month")
            print(f"\nSummary:\n  {recommendation.summary}")

            if recommendation.findings:
                print("\nFindings Detail:")
                for i, finding in enumerate(recommendation.findings, 1):
                    print(f"\n  [{i}] {finding.title}")
                    print(f"      Severity : {finding.severity.value}")
                    print(f"      Impact   : ${finding.estimated_monthly_usd:.2f}/month")
                    print(f"      Type     : {finding.finding_type}")
                    print(f"      Confidence: {finding.confidence:.0%}")
                    if finding.remediation_command:
                        print(f"      Remediation:\n        {finding.remediation_command[:200]}")
                    if finding.evidence:
                        print(f"      Evidence : {json.dumps(finding.evidence, indent=8)}")
        else:
            print("\nNo recommendation produced.")

        print("\n" + "=" * 70)

    except TimeoutError:
        print(f"\n[ERROR] Investigation timed out after {agent_config.investigation_timeout_sec}s",  # type: ignore[possibly-undefined]
              file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("local_run_error", error=str(exc), exc_info=True)
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(asyncio.run(main(trigger=args.trigger)))
