"""Unit tests for security posture tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from agent.tools.security import (
    _ACCESS_KEY_MAX_AGE_DAYS,
    get_cloudtrail_status,
    list_config_noncompliant_rules,
    list_guardduty_findings,
    list_iam_analyzer_findings,
    list_iam_credential_issues,
    list_open_security_groups,
    list_security_hub_findings,
)

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> Any:
    with open(_FIXTURES / name) as f:
        return json.load(f)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "op")


# ---------------------------------------------------------------------------
# TestListGuarddutyFindings
# ---------------------------------------------------------------------------


class TestListGuarddutyFindings:
    def test_active_finding_returned(self) -> None:
        data = _load("guardduty_response.json")
        mock_gd = MagicMock()
        mock_gd.list_detectors.return_value = {"DetectorIds": data["detector_ids"]}
        mock_gd.list_findings.return_value = {"FindingIds": [data["critical_finding"]["Id"]]}
        mock_gd.get_findings.return_value = {"Findings": [data["critical_finding"]]}

        with patch("agent.tools.security.get_client", return_value=mock_gd):
            result = list_guardduty_findings(region="us-east-1")

        assert len(result["findings"]) == 1
        finding = result["findings"][0]
        assert finding["finding_id"] == data["critical_finding"]["Id"]
        assert finding["type"] == data["critical_finding"]["Type"]
        assert finding["resource_id"] == "i-0abc123"
        assert result["detectors_checked"] == 1

    def test_no_detectors_returns_warning(self) -> None:
        mock_gd = MagicMock()
        mock_gd.list_detectors.return_value = {"DetectorIds": []}

        with patch("agent.tools.security.get_client", return_value=mock_gd):
            result = list_guardduty_findings(region="us-east-1")

        assert result["findings"] == []
        assert "warning" in result
        assert "GuardDuty not enabled" in result["warning"]

    def test_access_denied_returns_warning(self) -> None:
        mock_gd = MagicMock()
        mock_gd.list_detectors.side_effect = _client_error("AccessDeniedException")

        with patch("agent.tools.security.get_client", return_value=mock_gd):
            result = list_guardduty_findings(region="us-east-1")

        assert result["findings"] == []
        assert "warning" in result

    def test_severity_filter_excludes_low_score(self) -> None:
        # list_findings with low-severity finding ID — get_findings should not be called
        # because list_findings already filtered by score. Simulate empty finding IDs.
        mock_gd = MagicMock()
        mock_gd.list_detectors.return_value = {"DetectorIds": ["det123"]}
        mock_gd.list_findings.return_value = {"FindingIds": []}

        with patch("agent.tools.security.get_client", return_value=mock_gd):
            result = list_guardduty_findings(min_severity_score=4.0, region="us-east-1")

        assert result["findings"] == []
        mock_gd.get_findings.assert_not_called()

    def test_critical_severity_notional_value_is_500(self) -> None:
        data = _load("guardduty_response.json")
        mock_gd = MagicMock()
        mock_gd.list_detectors.return_value = {"DetectorIds": data["detector_ids"]}
        mock_gd.list_findings.return_value = {"FindingIds": [data["critical_finding"]["Id"]]}
        mock_gd.get_findings.return_value = {"Findings": [data["critical_finding"]]}

        with patch("agent.tools.security.get_client", return_value=mock_gd):
            result = list_guardduty_findings(region="us-east-1")

        assert result["findings"][0]["notional_monthly_usd"] == 500.0

    def test_high_severity_notional_value_is_100(self) -> None:
        data = _load("guardduty_response.json")
        mock_gd = MagicMock()
        mock_gd.list_detectors.return_value = {"DetectorIds": data["detector_ids"]}
        mock_gd.list_findings.return_value = {"FindingIds": [data["high_finding"]["Id"]]}
        mock_gd.get_findings.return_value = {"Findings": [data["high_finding"]]}

        with patch("agent.tools.security.get_client", return_value=mock_gd):
            result = list_guardduty_findings(region="us-east-1")

        assert result["findings"][0]["notional_monthly_usd"] == 100.0


# ---------------------------------------------------------------------------
# TestListConfigNoncompliantRules
# ---------------------------------------------------------------------------


class TestListConfigNoncompliantRules:
    def test_noncompliant_rules_returned(self) -> None:
        data = _load("config_compliance_response.json")
        mock_config = MagicMock()

        # Paginator mock
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"ComplianceByConfigRules": data["noncompliant_rules"]}
        ]
        mock_config.get_paginator.return_value = mock_paginator
        mock_config.get_compliance_details_by_config_rule.return_value = data["rule_details"][
            "restricted-ssh"
        ]

        with patch("agent.tools.security.get_client", return_value=mock_config):
            result = list_config_noncompliant_rules(region="us-east-1")

        assert len(result["rules"]) == 2
        rule_names = [r["rule_name"] for r in result["rules"]]
        assert "restricted-ssh" in rule_names

    def test_config_not_enabled_returns_warning(self) -> None:
        mock_config = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = _client_error("NoSuchConfigurationRecorderException")
        mock_config.get_paginator.return_value = mock_paginator

        with patch("agent.tools.security.get_client", return_value=mock_config):
            result = list_config_noncompliant_rules(region="us-east-1")

        assert result["rules"] == []
        assert "warning" in result

    def test_all_compliant_returns_empty_rules(self) -> None:
        mock_config = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"ComplianceByConfigRules": []}]
        mock_config.get_paginator.return_value = mock_paginator

        with patch("agent.tools.security.get_client", return_value=mock_config):
            result = list_config_noncompliant_rules(region="us-east-1")

        assert result["rules"] == []


# ---------------------------------------------------------------------------
# TestListIamAnalyzerFindings
# ---------------------------------------------------------------------------


class TestListIamAnalyzerFindings:
    def test_external_access_finding_returned(self) -> None:
        data = _load("iam_analyzer_response.json")
        mock_az = MagicMock()
        mock_az.list_analyzers.return_value = {"analyzers": data["analyzers"]}
        mock_az.list_findings.return_value = {
            "findings": [data["active_finding"]],
            "nextToken": None,
        }

        with patch("agent.tools.security.get_client", return_value=mock_az):
            result = list_iam_analyzer_findings(region="us-east-1")

        assert len(result["findings"]) == 1
        assert result["findings"][0]["finding_id"] == data["active_finding"]["id"]
        assert result["analyzers_checked"] == 1

    def test_no_analyzer_returns_warning(self) -> None:
        mock_az = MagicMock()
        mock_az.list_analyzers.return_value = {"analyzers": []}

        with patch("agent.tools.security.get_client", return_value=mock_az):
            result = list_iam_analyzer_findings(region="us-east-1")

        assert result["findings"] == []
        assert "warning" in result
        assert "No IAM Access Analyzer" in result["warning"]

    def test_archived_finding_excluded(self) -> None:
        data = _load("iam_analyzer_response.json")
        mock_az = MagicMock()
        mock_az.list_analyzers.return_value = {"analyzers": data["analyzers"]}
        # list_findings filter={"status": {"eq": ["ACTIVE"]}} returns only active ones
        # The mock returns only the active finding (archived is filtered by the API)
        mock_az.list_findings.return_value = {"findings": [data["active_finding"]]}

        with patch("agent.tools.security.get_client", return_value=mock_az):
            result = list_iam_analyzer_findings(region="us-east-1")

        assert all(f["finding_id"] != data["archived_finding"]["id"] for f in result["findings"])

    def test_access_denied_returns_warning(self) -> None:
        mock_az = MagicMock()
        mock_az.list_analyzers.side_effect = _client_error("AccessDeniedException")

        with patch("agent.tools.security.get_client", return_value=mock_az):
            result = list_iam_analyzer_findings(region="us-east-1")

        assert result["findings"] == []
        assert "warning" in result

    def test_finding_notional_value_is_250(self) -> None:
        data = _load("iam_analyzer_response.json")
        mock_az = MagicMock()
        mock_az.list_analyzers.return_value = {"analyzers": data["analyzers"]}
        mock_az.list_findings.return_value = {"findings": [data["active_finding"]]}

        with patch("agent.tools.security.get_client", return_value=mock_az):
            result = list_iam_analyzer_findings(region="us-east-1")

        assert result["findings"][0]["notional_monthly_usd"] == 250.0


# ---------------------------------------------------------------------------
# TestListSecurityHubFindings
# ---------------------------------------------------------------------------


class TestListSecurityHubFindings:
    def test_high_findings_returned(self) -> None:
        data = _load("security_hub_response.json")
        mock_hub = MagicMock()
        mock_hub.get_findings.return_value = {
            "Findings": [data["high_finding"], data["critical_finding"]]
        }

        with patch("agent.tools.security.get_client", return_value=mock_hub):
            result = list_security_hub_findings(min_severity="HIGH", region="us-east-1")

        assert len(result["findings"]) == 2

    def test_not_enabled_returns_warning(self) -> None:
        mock_hub = MagicMock()
        mock_hub.get_findings.side_effect = _client_error("InvalidAccessException")

        with patch("agent.tools.security.get_client", return_value=mock_hub):
            result = list_security_hub_findings(region="us-east-1")

        assert result["findings"] == []
        assert "warning" in result
        assert "Security Hub not enabled" in result["warning"]

    def test_medium_excluded_when_min_high(self) -> None:
        data = _load("security_hub_response.json")
        mock_hub = MagicMock()
        # Simulate API returning only HIGH+ when that filter is applied
        mock_hub.get_findings.return_value = {
            "Findings": [data["high_finding"], data["critical_finding"]]
        }

        with patch("agent.tools.security.get_client", return_value=mock_hub):
            result = list_security_hub_findings(min_severity="HIGH", region="us-east-1")

        severities = [f["severity"] for f in result["findings"]]
        assert "MEDIUM" not in severities

    def test_critical_included_when_min_high(self) -> None:
        data = _load("security_hub_response.json")
        mock_hub = MagicMock()
        mock_hub.get_findings.return_value = {"Findings": [data["critical_finding"]]}

        with patch("agent.tools.security.get_client", return_value=mock_hub):
            result = list_security_hub_findings(min_severity="HIGH", region="us-east-1")

        assert any(f["severity"] == "CRITICAL" for f in result["findings"])

    def test_critical_notional_value_is_500(self) -> None:
        data = _load("security_hub_response.json")
        mock_hub = MagicMock()
        mock_hub.get_findings.return_value = {"Findings": [data["critical_finding"]]}

        with patch("agent.tools.security.get_client", return_value=mock_hub):
            result = list_security_hub_findings(region="us-east-1")

        assert result["findings"][0]["notional_monthly_usd"] == 500.0


# ---------------------------------------------------------------------------
# TestGetCloudtrailStatus
# ---------------------------------------------------------------------------


class TestGetCloudtrailStatus:
    def test_multi_region_trail_active_no_gaps(self) -> None:
        data = _load("cloudtrail_response.json")
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {"trailList": [data["multi_region_trail"]]}
        mock_ct.get_trail_status.return_value = data["trail_status_active"]

        with patch("agent.tools.security.get_client", return_value=mock_ct):
            result = get_cloudtrail_status(region="us-east-1")

        assert result["has_multi_region_trail"] is True
        assert result["region_logging_active"] is True
        assert result["log_file_validation_enabled"] is True
        assert result["gaps"] == []

    def test_no_trails_returns_gap(self) -> None:
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {"trailList": []}

        with patch("agent.tools.security.get_client", return_value=mock_ct):
            result = get_cloudtrail_status(region="us-east-1")

        assert result["trails"] == []
        assert any("no trails" in g for g in result["gaps"])
        assert result["region_logging_active"] is False

    def test_trail_not_logging_detected(self) -> None:
        data = _load("cloudtrail_response.json")
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {"trailList": [data["multi_region_trail"]]}
        mock_ct.get_trail_status.return_value = data["trail_status_stopped"]

        with patch("agent.tools.security.get_client", return_value=mock_ct):
            result = get_cloudtrail_status(region="us-east-1")

        assert result["region_logging_active"] is False
        assert any("currently logging" in g for g in result["gaps"])

    def test_validation_disabled_detected(self) -> None:
        data = _load("cloudtrail_response.json")
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {
            "trailList": [data["single_region_trail_no_validation"]]
        }
        mock_ct.get_trail_status.return_value = data["trail_status_active"]

        with patch("agent.tools.security.get_client", return_value=mock_ct):
            result = get_cloudtrail_status(region="us-east-1")

        assert result["log_file_validation_enabled"] is False
        assert any("log file validation" in g for g in result["gaps"])

    def test_trail_metadata_in_response(self) -> None:
        data = _load("cloudtrail_response.json")
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {"trailList": [data["multi_region_trail"]]}
        mock_ct.get_trail_status.return_value = data["trail_status_active"]

        with patch("agent.tools.security.get_client", return_value=mock_ct):
            result = get_cloudtrail_status(region="us-east-1")

        assert len(result["trails"]) == 1
        trail = result["trails"][0]
        assert "trail_arn" in trail
        assert "s3_bucket" in trail
        assert trail["s3_bucket"] == "my-cloudtrail-bucket"


# ---------------------------------------------------------------------------
# TestListOpenSecurityGroups
# ---------------------------------------------------------------------------


class TestListOpenSecurityGroups:
    def _make_paginator(self, sgs: list[dict[str, Any]]) -> MagicMock:
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"SecurityGroups": sgs}]
        return mock_paginator

    def test_ssh_open_returns_critical(self) -> None:
        data = _load("security_groups_response.json")
        mock_ec2 = MagicMock()
        mock_ec2.get_paginator.return_value = self._make_paginator([data["ssh_open_sg"]])

        with patch("agent.tools.security.get_client", return_value=mock_ec2):
            result = list_open_security_groups(region="us-east-1")

        assert len(result["security_groups"]) == 1
        sg = result["security_groups"][0]
        assert sg["max_severity"] == "CRITICAL"
        assert any(r["port"] == 22 for r in sg["open_rules"])

    def test_mysql_open_returns_high(self) -> None:
        data = _load("security_groups_response.json")
        mock_ec2 = MagicMock()
        mock_ec2.get_paginator.return_value = self._make_paginator([data["mysql_open_sg"]])

        with patch("agent.tools.security.get_client", return_value=mock_ec2):
            result = list_open_security_groups(region="us-east-1")

        assert len(result["security_groups"]) == 1
        sg = result["security_groups"][0]
        assert sg["max_severity"] == "HIGH"
        assert any(r["port"] == 3306 for r in sg["open_rules"])

    def test_all_traffic_rule_returns_critical(self) -> None:
        data = _load("security_groups_response.json")
        mock_ec2 = MagicMock()
        mock_ec2.get_paginator.return_value = self._make_paginator([data["all_traffic_sg"]])

        with patch("agent.tools.security.get_client", return_value=mock_ec2):
            result = list_open_security_groups(region="us-east-1")

        assert result["security_groups"][0]["max_severity"] == "CRITICAL"
        assert any(r["port"] == "all" for r in result["security_groups"][0]["open_rules"])

    def test_ipv6_open_detected(self) -> None:
        data = _load("security_groups_response.json")
        mock_ec2 = MagicMock()
        mock_ec2.get_paginator.return_value = self._make_paginator([data["ipv6_ssh_sg"]])

        with patch("agent.tools.security.get_client", return_value=mock_ec2):
            result = list_open_security_groups(region="us-east-1")

        assert len(result["security_groups"]) == 1
        assert any(r["cidr"] == "::/0" for r in result["security_groups"][0]["open_rules"])

    def test_restricted_sg_not_returned(self) -> None:
        data = _load("security_groups_response.json")
        mock_ec2 = MagicMock()
        mock_ec2.get_paginator.return_value = self._make_paginator([data["restricted_sg"]])

        with patch("agent.tools.security.get_client", return_value=mock_ec2):
            result = list_open_security_groups(region="us-east-1")

        assert result["security_groups"] == []

    def test_no_open_groups_returns_empty(self) -> None:
        mock_ec2 = MagicMock()
        mock_ec2.get_paginator.return_value = self._make_paginator([])

        with patch("agent.tools.security.get_client", return_value=mock_ec2):
            result = list_open_security_groups(region="us-east-1")

        assert result["security_groups"] == []


# ---------------------------------------------------------------------------
# TestListIamCredentialIssues
# ---------------------------------------------------------------------------


def _make_iam_mock(
    *,
    root_mfa_enabled: bool = True,
    root_key_present: bool = False,
    csv_path: Path = _FIXTURES / "iam_credential_report.csv",
) -> MagicMock:
    mock_iam = MagicMock()
    mock_iam.get_account_summary.return_value = {
        "SummaryMap": {
            "AccountMFAEnabled": 1 if root_mfa_enabled else 0,
            "AccountAccessKeysPresent": 1 if root_key_present else 0,
        }
    }
    mock_iam.generate_credential_report.return_value = {"State": "COMPLETE"}
    with open(csv_path, "rb") as f:
        csv_bytes = f.read()
    mock_iam.get_credential_report.return_value = {"Content": csv_bytes}
    return mock_iam


class TestListIamCredentialIssues:
    def test_root_mfa_disabled_detected(self) -> None:
        mock_iam = _make_iam_mock(root_mfa_enabled=False)
        with patch("agent.tools.security.get_client", return_value=mock_iam):
            result = list_iam_credential_issues()

        assert result["root_mfa_enabled"] is False
        assert any(i["issue_type"] == "root_mfa_disabled" for i in result["issues"])
        root_issue = next(i for i in result["issues"] if i["issue_type"] == "root_mfa_disabled")
        assert root_issue["notional_monthly_usd"] == 500.0

    def test_root_access_key_detected(self) -> None:
        mock_iam = _make_iam_mock(root_key_present=True)
        with patch("agent.tools.security.get_client", return_value=mock_iam):
            result = list_iam_credential_issues()

        assert result["root_access_key_exists"] is True
        assert any(i["issue_type"] == "root_access_key_exists" for i in result["issues"])

    def test_user_without_mfa_detected(self) -> None:
        mock_iam = _make_iam_mock()
        with patch("agent.tools.security.get_client", return_value=mock_iam):
            result = list_iam_credential_issues()

        # alice has mfa_active=false in the CSV fixture
        usernames = [u["username"] for u in result["users_without_mfa"]]
        assert "alice" in usernames

    def test_stale_access_key_detected(self) -> None:
        # alice has key rotated 2025-07-01, which is > 90 days before today (2026-05-04)
        mock_iam = _make_iam_mock()
        with patch("agent.tools.security.get_client", return_value=mock_iam):
            result = list_iam_credential_issues()

        stale_usernames = [k["username"] for k in result["stale_access_keys"]]
        assert "alice" in stale_usernames
        alice_key = next(k for k in result["stale_access_keys"] if k["username"] == "alice")
        assert alice_key["age_days"] > _ACCESS_KEY_MAX_AGE_DAYS

    def test_fresh_key_not_flagged(self) -> None:
        # bob has key rotated 2026-04-15, which is ~19 days old (fresh)
        mock_iam = _make_iam_mock()
        with patch("agent.tools.security.get_client", return_value=mock_iam):
            result = list_iam_credential_issues()

        stale_usernames = [k["username"] for k in result["stale_access_keys"]]
        assert "bob" not in stale_usernames

    def test_region_param_ignored_iam_uses_us_east_1(self) -> None:
        mock_iam = _make_iam_mock()
        with patch("agent.tools.security.get_client", return_value=mock_iam) as mock_get_client:
            list_iam_credential_issues(region="eu-west-1")

        # get_client must always be called with "us-east-1", not "eu-west-1"
        mock_get_client.assert_called_once_with("iam", "us-east-1")

    def test_clean_account_returns_no_issues(self) -> None:
        # Build minimal CSV with only charlie (MFA enabled, no active keys)
        clean_csv = (
            "user,arn,user_creation_time,password_enabled,password_last_used,"
            "password_last_changed,mfa_active,access_key_1_active,"
            "access_key_1_last_rotated,access_key_2_active,access_key_2_last_rotated\n"
            "<root_account>,arn:aws:iam::123456789012:root,"
            "2020-01-01T00:00:00+00:00,not_supported,2026-04-01T00:00:00+00:00,"
            "not_supported,false,false,N/A,false,N/A\n"
            "charlie,arn:aws:iam::123456789012:user/charlie,"
            "2023-01-01T00:00:00+00:00,true,2026-04-20T00:00:00+00:00,"
            "2023-01-01T00:00:00+00:00,true,false,N/A,false,N/A\n"
        )
        mock_iam = MagicMock()
        mock_iam.get_account_summary.return_value = {
            "SummaryMap": {"AccountMFAEnabled": 1, "AccountAccessKeysPresent": 0}
        }
        mock_iam.generate_credential_report.return_value = {"State": "COMPLETE"}
        mock_iam.get_credential_report.return_value = {"Content": clean_csv.encode("utf-8")}

        with patch("agent.tools.security.get_client", return_value=mock_iam):
            result = list_iam_credential_issues()

        assert result["root_mfa_enabled"] is True
        assert result["root_access_key_exists"] is False
        assert result["users_without_mfa"] == []
        assert result["stale_access_keys"] == []
        assert result["issues"] == []
