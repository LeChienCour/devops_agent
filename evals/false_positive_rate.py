"""False-positive rate evaluator for FinOps agent findings.

Loads Finding fixtures from ``tests/fixtures/`` and applies a rule-based
classifier to measure false-positive rate without any LLM calls.

A finding is classified as a **true positive** when both conditions hold:
  - ``resource_id`` is not None (the finding is tied to a specific resource)
  - ``estimated_monthly_usd > 0`` (there is a measurable cost impact)

A finding is classified as a **false positive** when either condition fails:
  - ``resource_id`` is None  (no concrete resource identified)
  - ``estimated_monthly_usd == 0``  (zero dollar impact)

Usage (from repository root)::

    python -m evals.false_positive_rate
    python -m evals.false_positive_rate --fixtures path/to/fixtures.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default fixture path relative to this file's location
_REPO_ROOT = Path(__file__).parent.parent
_DEFAULT_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "findings_sample.json"


@dataclass
class EvalResult:
    """Aggregated false-positive evaluation result.

    Attributes:
        total: Total number of findings evaluated.
        true_positives: Findings with a concrete resource_id and cost > 0.
        false_positives: Findings missing a resource_id or with zero cost impact.
        fp_rate_pct: False-positive rate expressed as a percentage (0–100).
        fp_details: List of (finding_id, finding_type, reason) tuples for each FP.
    """

    total: int = 0
    true_positives: int = 0
    false_positives: int = 0
    fp_rate_pct: float = 0.0
    fp_details: list[tuple[str, str, str]] = field(default_factory=list)


def _classify_finding(finding: dict[str, Any]) -> tuple[bool, str]:
    """Apply rule-based true/false-positive classification to a raw finding dict.

    Rules (applied in order; first match wins):
      1. ``estimated_monthly_usd == 0``  → false positive (no measurable cost)
      2. ``resource_id is None``          → false positive (no concrete resource)
      3. Otherwise                        → true positive

    Args:
        finding: Raw finding dict loaded from JSON fixture.

    Returns:
        Tuple of ``(is_true_positive, reason_string)``.  When ``is_true_positive``
        is ``True`` the reason string is empty.
    """
    estimated_usd: float = float(finding.get("estimated_monthly_usd", 0))
    resource_id: str | None = finding.get("resource_id")

    if estimated_usd == 0:
        return False, "estimated_monthly_usd is 0 — no measurable cost impact"
    if resource_id is None:
        return False, "resource_id is None — finding not tied to a specific resource"
    return True, ""


def evaluate_findings(findings: list[dict[str, Any]]) -> EvalResult:
    """Classify each finding and compute aggregate false-positive metrics.

    Args:
        findings: List of raw finding dicts (as loaded from JSON).

    Returns:
        Populated EvalResult with counters and FP detail list.
    """
    result = EvalResult(total=len(findings))

    for finding in findings:
        finding_id: str = str(finding.get("finding_id", "unknown"))
        finding_type: str = str(finding.get("finding_type", "unknown"))

        is_tp, reason = _classify_finding(finding)
        if is_tp:
            result.true_positives += 1
        else:
            result.false_positives += 1
            result.fp_details.append((finding_id, finding_type, reason))

    if result.total > 0:
        result.fp_rate_pct = round(result.false_positives / result.total * 100, 2)

    return result


def load_findings_fixture(fixture_path: Path) -> list[dict[str, Any]]:
    """Load a JSON fixture file containing a list of finding objects.

    Args:
        fixture_path: Absolute or relative path to the JSON fixture file.

    Returns:
        List of raw finding dicts.

    Raises:
        FileNotFoundError: When the file does not exist.
        ValueError: When the JSON is not a list.
    """
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")

    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {fixture_path}, got {type(data).__name__}")
    return list(data)


def print_report(result: EvalResult, fixture_path: Path) -> None:
    """Print a human-readable evaluation report to stdout.

    Args:
        result: Computed EvalResult.
        fixture_path: Path to the fixture file used (shown in header).
    """
    separator = "-" * 60
    print(separator)
    print("FinOps Agent — False-Positive Rate Evaluation")
    print(f"Fixture : {fixture_path}")
    print(separator)
    print(f"Total findings    : {result.total}")
    print(f"True positives    : {result.true_positives}")
    print(f"False positives   : {result.false_positives}")
    print(f"FP rate           : {result.fp_rate_pct:.2f}%")

    if result.fp_details:
        print()
        print("False-positive detail:")
        for finding_id, finding_type, reason in result.fp_details:
            print(f"  [{finding_type}] {finding_id[:8]}... — {reason}")

    print(separator)


def run(fixture_path: Path | None = None) -> EvalResult:
    """Entry point for the evaluation harness.

    Args:
        fixture_path: Optional path override.  Defaults to
            ``tests/fixtures/findings_sample.json`` relative to the repo root.

    Returns:
        EvalResult with all metrics populated.
    """
    path = fixture_path or _DEFAULT_FIXTURE
    findings = load_findings_fixture(path)
    result = evaluate_findings(findings)
    print_report(result, path)
    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure false-positive rate against FinOps agent finding fixtures."
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=None,
        help="Path to a JSON fixture file (default: tests/fixtures/findings_sample.json)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    run(fixture_path=args.fixtures)
