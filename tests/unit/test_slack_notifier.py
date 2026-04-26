"""Unit tests for notifications.slack_notifier.SlackNotifier.

All HTTP calls (urllib.request.urlopen) and SSM calls
(common.secrets.get_slack_webhook_url) are fully mocked — no network or AWS
access required.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agent.models.finding import Finding, Recommendation, Severity
from notifications.slack_notifier import (
    _SEVERITY_EMOJI,
    SlackNotifier,
    _build_payload,
    _truncate,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_WEBHOOK = "https://hooks.slack.com/services/TEST/WEBHOOK/URL"
_INVESTIGATION_ID = "inv-unit-0001"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_finding(**overrides: Any) -> Finding:
    """Return a minimal valid Finding with optional field overrides."""
    base: dict[str, Any] = {
        "finding_type": "unattached_ebs",
        "severity": Severity.HIGH,
        "title": "Unattached EBS Volume",
        "description": "Volume vol-0abc is not attached to any instance.",
        "resource_id": "vol-0abc123",
        "estimated_monthly_usd": 45.0,
        "confidence": 0.90,
        "remediation_command": "aws ec2 delete-volume --volume-id vol-0abc123",
        "evidence": {"region": "us-east-1"},
    }
    base.update(overrides)
    return Finding(**base)


def _make_recommendation(
    findings: list[Finding] | None = None,
    summary: str = "Test summary",
) -> Recommendation:
    """Return a Recommendation wrapping the given findings."""
    if findings is None:
        findings = [_make_finding()]
    total_usd = sum(f.estimated_monthly_usd for f in findings)
    return Recommendation(
        findings=findings,
        total_estimated_monthly_usd=total_usd,
        summary=summary,
        investigation_id=_INVESTIGATION_ID,
    )


def _make_notifier() -> SlackNotifier:
    """Return a SlackNotifier backed by a mock AgentConfig."""
    config = MagicMock()
    config.aws_region = "us-east-1"
    return SlackNotifier(config=config)


@pytest.fixture()
def mock_urlopen() -> Any:
    """Patch urllib.request.urlopen; yields a mock response with status=200."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch(
        "notifications.slack_notifier.urllib.request.urlopen", return_value=mock_response
    ) as m:
        yield m


@pytest.fixture()
def mock_webhook() -> Any:
    """Patch get_slack_webhook_url to return a deterministic test URL."""
    with patch(
        "notifications.slack_notifier.get_slack_webhook_url",
        return_value=_TEST_WEBHOOK,
    ) as m:
        yield m


# ---------------------------------------------------------------------------
# _truncate helper tests
# ---------------------------------------------------------------------------


class TestTruncate:
    """Tests for the _truncate helper."""

    def test_truncate_short_string_unchanged(self) -> None:
        """Strings at or under the limit must be returned unchanged."""
        assert _truncate("hello", 10) == "hello"

    def test_truncate_exact_length_unchanged(self) -> None:
        """String exactly at the limit must not be truncated."""
        text = "a" * 20
        assert _truncate(text, 20) == text

    def test_truncate_long_string_ends_with_ellipsis(self) -> None:
        """Strings exceeding the limit must end with the ellipsis character."""
        result = _truncate("a" * 200, 150)
        assert result.endswith("…")

    def test_truncate_long_string_total_length_correct(self) -> None:
        """Truncated string length must equal max_len exactly."""
        result = _truncate("x" * 200, 150)
        assert len(result) == 150


# ---------------------------------------------------------------------------
# Severity emoji mapping tests
# ---------------------------------------------------------------------------


class TestSeverityEmojiMap:
    """Verify _SEVERITY_EMOJI covers all Severity values."""

    def test_critical_emoji(self) -> None:
        assert _SEVERITY_EMOJI[Severity.CRITICAL] == "🔴"

    def test_high_emoji(self) -> None:
        assert _SEVERITY_EMOJI[Severity.HIGH] == "🟠"

    def test_medium_emoji(self) -> None:
        assert _SEVERITY_EMOJI[Severity.MEDIUM] == "🟡"

    def test_low_emoji(self) -> None:
        assert _SEVERITY_EMOJI[Severity.LOW] == "🟢"

    def test_all_severity_values_mapped(self) -> None:
        """Every member of the Severity enum must have an entry in the map."""
        for sev in Severity:
            assert sev in _SEVERITY_EMOJI, f"{sev} missing from _SEVERITY_EMOJI"


# ---------------------------------------------------------------------------
# _build_payload structure tests
# ---------------------------------------------------------------------------


class TestBuildPayload:
    """Tests for the _build_payload message builder."""

    def test_payload_has_blocks_key(self) -> None:
        rec = _make_recommendation()
        payload = _build_payload(rec, _INVESTIGATION_ID)
        assert "blocks" in payload

    def test_payload_first_block_is_header(self) -> None:
        rec = _make_recommendation()
        payload = _build_payload(rec, _INVESTIGATION_ID)
        assert payload["blocks"][0]["type"] == "header"

    def test_payload_header_contains_finops_report(self) -> None:
        rec = _make_recommendation()
        payload = _build_payload(rec, _INVESTIGATION_ID)
        header_text: str = payload["blocks"][0]["text"]["text"]
        assert "FinOps Weekly Report" in header_text

    def test_payload_context_block_contains_investigation_id(self) -> None:
        rec = _make_recommendation()
        payload = _build_payload(rec, _INVESTIGATION_ID)
        # Second block is the context with the investigation ID
        context_block = payload["blocks"][1]
        assert context_block["type"] == "context"
        context_text: str = context_block["elements"][0]["text"]
        assert _INVESTIGATION_ID in context_text

    def test_payload_summary_section_contains_total_savings(self) -> None:
        rec = _make_recommendation([_make_finding(estimated_monthly_usd=75.50)])
        payload = _build_payload(rec, _INVESTIGATION_ID)
        # Third block (index 2) is the executive summary section
        section = payload["blocks"][2]
        assert section["type"] == "section"
        assert "75.50" in section["text"]["text"]

    def test_payload_findings_sorted_descending_by_usd(self) -> None:
        """Findings must appear in the payload sorted by estimated_monthly_usd desc."""
        findings = [
            _make_finding(title="Cheap", estimated_monthly_usd=5.0),
            _make_finding(title="Expensive", estimated_monthly_usd=200.0),
            _make_finding(title="Medium", estimated_monthly_usd=50.0),
        ]
        rec = _make_recommendation(findings)
        payload = _build_payload(rec, _INVESTIGATION_ID)
        # Collect all section block texts that mention a title
        section_texts = [
            b["text"]["text"]
            for b in payload["blocks"]
            if b.get("type") == "section" and "text" in b
        ]
        # Filter out the summary section (doesn't contain finding titles directly)
        finding_texts = [t for t in section_texts if any(f.title in t for f in findings)]
        # Expensive should appear before Cheap
        expensive_idx = next(i for i, t in enumerate(finding_texts) if "Expensive" in t)
        cheap_idx = next(i for i, t in enumerate(finding_texts) if "Cheap" in t)
        assert expensive_idx < cheap_idx

    def test_payload_max_10_findings(self) -> None:
        """Payload must include at most 10 findings even when more are present."""
        findings = [
            _make_finding(
                title=f"Finding {i}",
                estimated_monthly_usd=float(i),
                resource_id=f"vol-{i:04d}",
            )
            for i in range(15)
        ]
        rec = _make_recommendation(findings)
        payload = _build_payload(rec, _INVESTIGATION_ID)
        section_blocks_with_mo = [
            b
            for b in payload["blocks"]
            if b.get("type") == "section" and b.get("text", {}).get("text", "").endswith("/mo")
        ]
        assert len(section_blocks_with_mo) <= 10

    def test_payload_remediation_command_rendered_as_code_block(self) -> None:
        finding = _make_finding(remediation_command="aws ec2 delete-volume --volume-id vol-xyz")
        rec = _make_recommendation([finding])
        payload = _build_payload(rec, _INVESTIGATION_ID)
        all_texts = [
            elem["text"]
            for b in payload["blocks"]
            if b.get("type") == "context"
            for elem in b.get("elements", [])
        ]
        remediation_texts = [t for t in all_texts if "delete-volume" in t]
        assert len(remediation_texts) == 1
        assert remediation_texts[0].startswith("```")
        assert remediation_texts[0].endswith("```")

    def test_payload_no_remediation_block_when_command_is_none(self) -> None:
        finding = _make_finding(remediation_command=None)
        rec = _make_recommendation([finding])
        payload = _build_payload(rec, _INVESTIGATION_ID)
        all_texts = [
            elem["text"]
            for b in payload["blocks"]
            if b.get("type") == "context"
            for elem in b.get("elements", [])
        ]
        code_blocks = [t for t in all_texts if t.startswith("```")]
        assert len(code_blocks) == 0

    def test_payload_footer_contains_finops_agent(self) -> None:
        rec = _make_recommendation()
        payload = _build_payload(rec, _INVESTIGATION_ID)
        last_block = payload["blocks"][-1]
        assert last_block["type"] == "context"
        footer_text: str = last_block["elements"][0]["text"]
        assert "FinOps Agent" in footer_text

    def test_payload_severity_emoji_present_in_finding_section(self) -> None:
        finding = _make_finding(severity=Severity.CRITICAL)
        rec = _make_recommendation([finding])
        payload = _build_payload(rec, _INVESTIGATION_ID)
        section_texts = [
            b["text"]["text"]
            for b in payload["blocks"]
            if b.get("type") == "section" and b.get("text", {}).get("text", "").endswith("/mo")
        ]
        assert any("🔴" in t for t in section_texts)


# ---------------------------------------------------------------------------
# SlackNotifier.notify — happy path tests
# ---------------------------------------------------------------------------


class TestSlackNotifierNotify:
    """Tests for SlackNotifier.notify."""

    def test_notify_calls_urlopen_once(self, mock_urlopen: Any, mock_webhook: Any) -> None:
        """notify must perform exactly one HTTP POST for a non-empty recommendation."""
        notifier = _make_notifier()
        rec = _make_recommendation()
        notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)
        mock_urlopen.assert_called_once()

    def test_notify_posts_to_correct_url(self, mock_urlopen: Any, mock_webhook: Any) -> None:
        """The Request passed to urlopen must target the webhook URL."""
        notifier = _make_notifier()
        rec = _make_recommendation()
        notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)
        request_arg = mock_urlopen.call_args[0][0]
        assert request_arg.full_url == _TEST_WEBHOOK

    def test_notify_posts_valid_json_body(self, mock_urlopen: Any, mock_webhook: Any) -> None:
        """The request body must be valid JSON containing a 'blocks' key."""
        notifier = _make_notifier()
        rec = _make_recommendation()
        notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)
        request_arg = mock_urlopen.call_args[0][0]
        body = json.loads(request_arg.data.decode("utf-8"))
        assert "blocks" in body

    def test_notify_content_type_header_is_json(self, mock_urlopen: Any, mock_webhook: Any) -> None:
        """The POST must include Content-Type: application/json."""
        notifier = _make_notifier()
        rec = _make_recommendation()
        notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)
        request_arg = mock_urlopen.call_args[0][0]
        assert request_arg.get_header("Content-type") == "application/json"

    def test_notify_skips_http_call_when_findings_empty(
        self, mock_urlopen: Any, mock_webhook: Any
    ) -> None:
        """notify must NOT call urlopen when recommendation.findings is empty."""
        notifier = _make_notifier()
        rec = _make_recommendation(findings=[])
        notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)
        mock_urlopen.assert_not_called()

    def test_notify_skips_ssm_call_when_findings_empty(self, mock_webhook: Any) -> None:
        """SSM must NOT be called when there are no findings (no HTTP call needed)."""
        notifier = _make_notifier()
        rec = _make_recommendation(findings=[])
        notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)
        mock_webhook.assert_not_called()


# ---------------------------------------------------------------------------
# SlackNotifier.notify — error handling tests
# ---------------------------------------------------------------------------


class TestSlackNotifierErrorHandling:
    """Tests that exceptions from urlopen/SSM are swallowed and logged."""

    def test_notify_does_not_reraise_on_urlopen_error(
        self, mock_webhook: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """urlopen raising any exception must not propagate out of notify."""
        with patch(
            "notifications.slack_notifier.urllib.request.urlopen",
            side_effect=OSError("connection refused"),
        ):
            notifier = _make_notifier()
            rec = _make_recommendation()
            # Must not raise
            notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)

    def test_notify_logs_slack_notification_failed_on_urlopen_error(
        self, mock_webhook: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """On urlopen failure the event 'slack_notification_failed' must be logged."""
        with patch(
            "notifications.slack_notifier.urllib.request.urlopen",
            side_effect=OSError("connection refused"),
        ):
            notifier = _make_notifier()
            rec = _make_recommendation()
            notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)

        captured = capsys.readouterr().out
        assert "slack_notification_failed" in captured

    def test_notify_does_not_reraise_on_ssm_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """SSM fetch failure must be swallowed and logged, not re-raised."""
        with patch(
            "notifications.slack_notifier.get_slack_webhook_url",
            side_effect=RuntimeError("SSM unavailable"),
        ):
            notifier = _make_notifier()
            rec = _make_recommendation()
            notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)

        captured = capsys.readouterr().out
        assert "slack_notification_failed" in captured

    def test_notify_logs_error_string_on_failure(
        self, mock_webhook: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The logged error must include a string representation of the exception."""
        error_msg = "timeout exceeded"
        with patch(
            "notifications.slack_notifier.urllib.request.urlopen",
            side_effect=TimeoutError(error_msg),
        ):
            notifier = _make_notifier()
            rec = _make_recommendation()
            notifier.notify(recommendation=rec, investigation_id=_INVESTIGATION_ID)

        captured = capsys.readouterr().out
        assert error_msg in captured
