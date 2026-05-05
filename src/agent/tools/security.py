"""Security posture tools — in-process wrappers used by the LangGraph agent.

Covers: GuardDuty, AWS Config, IAM Access Analyzer, Security Hub,
CloudTrail, EC2 Security Groups, IAM Credential Hygiene.

Notional risk values (estimated_monthly_usd):
    Security findings represent risk exposure, not direct cost waste.
    Notional USD values are assigned so findings pass the recommend_node
    cost_threshold_usd filter (default $5.0) and give the LLM a relative
    risk signal:

        GuardDuty CRITICAL (score >= 7.0)   $500 / month
        GuardDuty HIGH     (score >= 4.0)   $100 / month
        IAM root MFA disabled               $500 / month
        IAM root access key exists          $500 / month
        IAM Access Analyzer external access $250 / month
        CloudTrail gap                      $150 / month
        Open SG CRITICAL port (SSH/RDP)     $300 / month
        Open SG HIGH port (DB/services)     $100 / month
        IAM user without MFA                 $50 / month per user
        IAM stale access key (>90 days)      $30 / month per key
        Config NON_COMPLIANT critical rule   $200 / month
        Config NON_COMPLIANT rule            $50  / month
        Security Hub CRITICAL               $500 / month
        Security Hub HIGH                   $100 / month
        Security Hub MEDIUM                  $25 / month
"""

from __future__ import annotations

import csv
import io
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from common.aws_clients import get_client

logger = Logger(service="finops-agent")

_IAM_REGION = "us-east-1"
_ACCESS_KEY_MAX_AGE_DAYS = 90
_CREDENTIAL_REPORT_MAX_ATTEMPTS = 5
_CREDENTIAL_REPORT_POLL_SLEEP = 2.0

_CRITICAL_PORTS: dict[int, str] = {
    22: "SSH",
    23: "Telnet",
    3389: "RDP",
    5900: "VNC",
}
_HIGH_PORTS: dict[int, str] = {
    135: "RPC",
    445: "SMB",
    1433: "MSSQL",
    2181: "ZooKeeper",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    8080: "HTTP-alt",
    8443: "HTTPS-alt",
    9200: "Elasticsearch HTTP",
    9300: "Elasticsearch Transport",
    11211: "Memcached",
    27017: "MongoDB",
}

_SEVERITY_ORDER = ["INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_guardduty_findings",
        "description": (
            "Lists active GuardDuty threat findings at or above a minimum severity score. "
            "Returns HIGH and CRITICAL findings with threat type, resource affected, and "
            "severity score. Returns an empty list with a warning if GuardDuty is not enabled."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_severity_score": {
                    "type": "number",
                    "description": (
                        "Minimum GuardDuty severity score to include (1.0–10.0). "
                        "Defaults to 4.0 (HIGH threshold)."
                    ),
                    "default": 4.0,
                },
                "region": {
                    "type": "string",
                    "description": "AWS region to query. Defaults to us-east-1.",
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_config_noncompliant_rules",
        "description": (
            "Lists AWS Config rules with NON_COMPLIANT resources. "
            "Each non-compliant rule indicates a policy violation that may represent "
            "a security or compliance gap. Returns an empty list with a warning if "
            "AWS Config is not enabled in the region."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "AWS region to query. Defaults to us-east-1.",
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_iam_analyzer_findings",
        "description": (
            "Lists IAM Access Analyzer findings for external access to account resources. "
            "External access findings indicate S3 buckets, IAM roles, KMS keys, or other "
            "resources that grant access to principals outside the account. "
            "Returns an empty list with a warning if no analyzer is enabled."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "AWS region to query. Defaults to us-east-1.",
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_security_hub_findings",
        "description": (
            "Lists aggregated Security Hub findings at or above a minimum severity. "
            "Security Hub aggregates findings from GuardDuty, Inspector, Macie, and "
            "third-party integrations. Returns an empty list with a warning if "
            "Security Hub is not enabled."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_severity": {
                    "type": "string",
                    "enum": ["INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    "description": "Minimum Security Hub severity label. Defaults to HIGH.",
                    "default": "HIGH",
                },
                "region": {
                    "type": "string",
                    "description": "AWS region to query. Defaults to us-east-1.",
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_cloudtrail_status",
        "description": (
            "Returns CloudTrail trail configuration: which trails are enabled, "
            "whether multi-region logging is active, and whether log file validation "
            "is enabled. Identifies regions not covered by any trail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "AWS region to query for trail configuration.",
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_open_security_groups",
        "description": (
            "Lists EC2 security groups with ingress rules allowing traffic from "
            "0.0.0.0/0 (all IPv4) or ::/0 (all IPv6) on critical or high-risk ports. "
            "Critical ports include SSH (22), RDP (3389), VNC (5900), Telnet (23). "
            "High-risk ports include databases (MySQL, PostgreSQL, MSSQL, MongoDB, Redis) "
            "and common service ports."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "AWS region to query. Defaults to us-east-1.",
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_iam_credential_issues",
        "description": (
            "Audits IAM credential hygiene across the account: checks for root MFA disabled, "
            "root access keys existing, IAM users without MFA, and access keys older than 90 days. "
            "IAM is a global service — the region parameter is ignored."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": (
                        "Ignored — IAM is a global service. Included for interface consistency."
                    ),
                    "default": "us-east-1",
                },
            },
            "required": [],
        },
    },
]


def list_guardduty_findings(
    min_severity_score: float = 4.0,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return active GuardDuty findings at or above the given severity score.

    Args:
        min_severity_score: Minimum severity (1.0–10.0). Defaults to 4.0 (HIGH).
        region: AWS region to query.

    Returns:
        Dict with ``findings`` list and ``detectors_checked`` count.
        Returns ``warning`` key if GuardDuty is not enabled.
    """
    gd = get_client("guardduty", region)

    try:
        detectors_response = gd.list_detectors()
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ("AccessDeniedException", "BadRequestException"):
            logger.warning("guardduty_not_accessible", region=region, error_code=error_code)
            return {"findings": [], "warning": f"GuardDuty not enabled in region {region}"}
        raise

    detector_ids: list[str] = detectors_response.get("DetectorIds", [])
    if not detector_ids:
        logger.info("guardduty_no_detectors", region=region)
        return {"findings": [], "warning": f"GuardDuty not enabled in region {region}"}

    all_findings: list[dict[str, Any]] = []

    for detector_id in detector_ids:
        finding_ids: list[str] = []
        paginator_kwargs: dict[str, Any] = {
            "DetectorId": detector_id,
            "FindingCriteria": {
                "Criterion": {
                    "service.archived": {"Eq": ["false"]},
                    "severity": {"Gte": int(min_severity_score)},
                }
            },
        }

        # list_findings paginates via NextToken
        next_token: str | None = None
        while True:
            if next_token:
                paginator_kwargs["NextToken"] = next_token
            response = gd.list_findings(**paginator_kwargs)
            finding_ids.extend(response.get("FindingIds", []))
            next_token = response.get("NextToken")
            if not next_token:
                break

        # get_findings accepts up to 50 IDs per call
        for i in range(0, len(finding_ids), 50):
            batch = finding_ids[i : i + 50]
            details_response = gd.get_findings(DetectorId=detector_id, FindingIds=batch)
            for raw in details_response.get("Findings", []):
                severity_score: float = float(raw.get("Severity", 0.0))
                notional_usd = 500.0 if severity_score >= 7.0 else 100.0
                resource = raw.get("Resource", {})
                resource_type: str = resource.get("ResourceType", "Unknown")
                resource_id = _extract_guardduty_resource_id(resource, resource_type)
                all_findings.append(
                    {
                        "finding_id": raw.get("Id"),
                        "type": raw.get("Type"),
                        "severity_score": severity_score,
                        "title": raw.get("Title"),
                        "description": raw.get("Description"),
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "region": raw.get("Region"),
                        "created_at": str(raw.get("CreatedAt", "")),
                        "updated_at": str(raw.get("UpdatedAt", "")),
                        "notional_monthly_usd": notional_usd,
                    }
                )

    logger.info("list_guardduty_findings_complete", count=len(all_findings), region=region)
    return {"findings": all_findings, "detectors_checked": len(detector_ids)}


def _extract_guardduty_resource_id(resource: dict[str, Any], resource_type: str) -> str | None:
    """Extract a human-readable resource ID from a GuardDuty resource dict."""
    if resource_type == "Instance":
        details = resource.get("InstanceDetails", {})
        return str(details.get("InstanceId", "")) or None
    if resource_type == "S3Bucket":
        buckets = resource.get("S3BucketDetails", [])
        if buckets:
            return str(buckets[0].get("Name", "")) or None
    if resource_type == "AccessKey":
        details = resource.get("AccessKeyDetails", {})
        return str(details.get("UserName", "")) or None
    return None


def list_config_noncompliant_rules(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return AWS Config rules that have NON_COMPLIANT resources.

    Args:
        region: AWS region to query.

    Returns:
        Dict with ``rules`` list. Each entry contains rule_name,
        noncompliant_resource_count, and sample resources.
        Returns ``warning`` key if AWS Config is not enabled.
    """
    config = get_client("config", region)

    try:
        paginator = config.get_paginator("describe_compliance_by_config_rule")
        pages = paginator.paginate(ComplianceTypes=["NON_COMPLIANT"])
        noncompliant_rule_names: list[str] = []
        for page in pages:
            for item in page.get("ComplianceByConfigRules", []):
                if item.get("Compliance", {}).get("ComplianceType") == "NON_COMPLIANT":
                    noncompliant_rule_names.append(item["ConfigRuleName"])
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in (
            "NoSuchConfigurationRecorderException",
            "NoSuchDeliveryChannelException",
        ):
            logger.warning("config_not_enabled", region=region, error_code=error_code)
            return {"rules": [], "warning": "AWS Config not enabled in this region"}
        raise

    rules: list[dict[str, Any]] = []
    for rule_name in noncompliant_rule_names[:100]:  # cap at 100 to avoid Lambda timeout
        try:
            details_response = config.get_compliance_details_by_config_rule(
                ConfigRuleName=rule_name,
                ComplianceTypes=["NON_COMPLIANT"],
            )
        except ClientError:
            logger.warning("config_rule_details_error", rule_name=rule_name)
            rules.append(
                {
                    "rule_name": rule_name,
                    "noncompliant_resource_count": -1,
                    "resources": [],
                }
            )
            continue

        evaluations = details_response.get("EvaluationResults", [])
        sample_resources = [
            {
                "resource_type": e.get("EvaluationResultIdentifier", {})
                .get("EvaluationResultQualifier", {})
                .get("ResourceType"),
                "resource_id": e.get("EvaluationResultIdentifier", {})
                .get("EvaluationResultQualifier", {})
                .get("ResourceId"),
            }
            for e in evaluations[:5]
        ]
        rules.append(
            {
                "rule_name": rule_name,
                "noncompliant_resource_count": len(evaluations),
                "resources": sample_resources,
            }
        )

    logger.info("list_config_noncompliant_rules_complete", count=len(rules), region=region)
    return {"rules": rules}


def list_iam_analyzer_findings(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return active IAM Access Analyzer findings for external resource access.

    Args:
        region: AWS region to query.

    Returns:
        Dict with ``findings`` list and ``analyzers_checked`` count.
        Returns ``warning`` key if no analyzer is enabled.
    """
    analyzer = get_client("accessanalyzer", region)

    try:
        analyzers_response = analyzer.list_analyzers(type="ACCOUNT")
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "AccessDeniedException":
            logger.warning("iam_analyzer_access_denied", region=region)
            return {
                "findings": [],
                "warning": f"IAM Access Analyzer not accessible in region {region}",
            }
        raise

    analyzers = analyzers_response.get("analyzers", [])
    if not analyzers:
        logger.info("iam_analyzer_none_enabled", region=region)
        return {"findings": [], "warning": "No IAM Access Analyzer enabled in this region"}

    all_findings: list[dict[str, Any]] = []

    for az in analyzers:
        analyzer_arn: str = az["arn"]
        next_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "analyzerArn": analyzer_arn,
                "filter": {"status": {"eq": ["ACTIVE"]}},
            }
            if next_token:
                kwargs["nextToken"] = next_token
            response = analyzer.list_findings(**kwargs)
            for f in response.get("findings", []):
                all_findings.append(
                    {
                        "finding_id": f.get("id"),
                        "resource_type": f.get("resourceType"),
                        "resource": f.get("resource"),
                        "is_public": f.get("isPublic", False),
                        "action": f.get("action", []),
                        "principal": f.get("principal", {}),
                        "condition": f.get("condition", {}),
                        "analyzed_at": str(f.get("analyzedAt", "")),
                        "notional_monthly_usd": 250.0,
                    }
                )
            next_token = response.get("nextToken")
            if not next_token:
                break

    logger.info("list_iam_analyzer_findings_complete", count=len(all_findings), region=region)
    return {"findings": all_findings, "analyzers_checked": len(analyzers)}


def list_security_hub_findings(
    min_severity: str = "HIGH",
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return aggregated Security Hub findings at or above the minimum severity.

    Args:
        min_severity: Minimum severity label (INFORMATIONAL/LOW/MEDIUM/HIGH/CRITICAL).
        region: AWS region to query.

    Returns:
        Dict with ``findings`` list (capped at 100) and ``total_returned`` count.
        Returns ``warning`` key if Security Hub is not enabled.
    """
    hub = get_client("securityhub", region)

    # Build the set of severity labels to include
    min_idx = _SEVERITY_ORDER.index(min_severity) if min_severity in _SEVERITY_ORDER else 3
    severity_labels = _SEVERITY_ORDER[min_idx:]

    filters: dict[str, Any] = {
        "SeverityLabel": [{"Value": label, "Comparison": "EQUALS"} for label in severity_labels],
        "RecordState": [{"Value": "ACTIVE", "Comparison": "EQUALS"}],
        "WorkflowStatus": [{"Value": "NEW", "Comparison": "EQUALS"}],
    }

    try:
        response = hub.get_findings(Filters=filters, MaxResults=100)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "InvalidAccessException":
            logger.warning("security_hub_not_enabled", region=region)
            return {
                "findings": [],
                "warning": f"Security Hub not enabled in region {region}",
            }
        raise

    _notional: dict[str, float] = {"CRITICAL": 500.0, "HIGH": 100.0, "MEDIUM": 25.0}

    findings: list[dict[str, Any]] = []
    for raw in response.get("Findings", []):
        severity_label: str = raw.get("Severity", {}).get("Label", "HIGH")
        resources = raw.get("Resources", [{}])
        first_resource = resources[0] if resources else {}
        findings.append(
            {
                "finding_id": raw.get("Id"),
                "title": raw.get("Title"),
                "description": raw.get("Description"),
                "severity": severity_label,
                "product_arn": raw.get("ProductArn"),
                "resource_id": first_resource.get("Id"),
                "resource_type": first_resource.get("Type"),
                "updated_at": raw.get("UpdatedAt"),
                "notional_monthly_usd": _notional.get(severity_label, 25.0),
            }
        )

    logger.info("list_security_hub_findings_complete", count=len(findings), region=region)
    return {"findings": findings, "total_returned": len(findings)}


def get_cloudtrail_status(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return CloudTrail trail configuration and identify logging gaps.

    Args:
        region: AWS region to query.

    Returns:
        Dict with ``trails`` list, ``has_multi_region_trail`` bool,
        ``region_logging_active`` bool, ``log_file_validation_enabled`` bool,
        and ``gaps`` list of human-readable gap descriptions.
    """
    ct = get_client("cloudtrail", region)

    trails_response = ct.describe_trails(includeShadowTrails=False)
    trail_list = trails_response.get("trailList", [])

    if not trail_list:
        return {
            "trails": [],
            "has_multi_region_trail": False,
            "region_logging_active": False,
            "log_file_validation_enabled": False,
            "gaps": ["no trails configured — CloudTrail not enabled in this region"],
        }

    enriched_trails: list[dict[str, Any]] = []
    for trail in trail_list:
        trail_arn: str = trail.get("TrailARN", trail.get("Name", ""))
        try:
            status = ct.get_trail_status(Name=trail_arn)
        except ClientError:
            status = {}

        enriched_trails.append(
            {
                "trail_arn": trail_arn,
                "name": trail.get("Name"),
                "is_multi_region": trail.get("IsMultiRegionTrail", False),
                "log_file_validation_enabled": trail.get("LogFileValidationEnabled", False),
                "s3_bucket": trail.get("S3BucketName"),
                "cloudwatch_logs_group": trail.get("CloudWatchLogsLogGroupArn"),
                "home_region": trail.get("HomeRegion"),
                "is_logging": status.get("IsLogging", False),
                "latest_delivery_error": status.get("LatestDeliveryError"),
            }
        )

    has_multi_region = any(t["is_multi_region"] for t in enriched_trails)
    region_logging_active = any(t["is_logging"] for t in enriched_trails)
    all_validation_enabled = all(t["log_file_validation_enabled"] for t in enriched_trails)

    gaps: list[str] = []
    if not has_multi_region:
        gaps.append("no multi-region trail — other regions may not be logged")
    if not region_logging_active:
        gaps.append("no trail is currently logging in this region")
    if not all_validation_enabled:
        gaps.append("log file validation disabled — log tampering cannot be detected")

    logger.info(
        "get_cloudtrail_status_complete",
        trail_count=len(enriched_trails),
        gaps=len(gaps),
        region=region,
    )
    return {
        "trails": enriched_trails,
        "has_multi_region_trail": has_multi_region,
        "region_logging_active": region_logging_active,
        "log_file_validation_enabled": all_validation_enabled,
        "gaps": gaps,
    }


def list_open_security_groups(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return EC2 security groups with public ingress on critical or high-risk ports.

    Flags rules that allow 0.0.0.0/0 or ::/0 on ports in _CRITICAL_PORTS or
    _HIGH_PORTS, plus all-traffic rules (protocol -1).

    Args:
        region: AWS region to query.

    Returns:
        Dict with ``security_groups`` list. Each entry contains group_id,
        group_name, vpc_id, open_rules, and max_severity.
    """
    ec2 = get_client("ec2", region)

    paginator = ec2.get_paginator("describe_security_groups")
    open_groups: list[dict[str, Any]] = []

    for page in paginator.paginate():
        for sg in page.get("SecurityGroups", []):
            open_rules: list[dict[str, Any]] = []
            for rule in sg.get("IpPermissions", []):
                matched = _check_sg_rule_for_public_access(rule)
                open_rules.extend(matched)

            if not open_rules:
                continue

            max_severity = (
                "CRITICAL" if any(r["severity"] == "CRITICAL" for r in open_rules) else "HIGH"
            )
            open_groups.append(
                {
                    "group_id": sg.get("GroupId"),
                    "group_name": sg.get("GroupName"),
                    "vpc_id": sg.get("VpcId"),
                    "description": sg.get("Description"),
                    "open_rules": open_rules,
                    "max_severity": max_severity,
                }
            )

    logger.info("list_open_security_groups_complete", count=len(open_groups), region=region)
    return {"security_groups": open_groups}


def _check_sg_rule_for_public_access(rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Return open-access rule entries for a single SG inbound rule dict."""
    public_cidrs = [
        r.get("CidrIp", "") for r in rule.get("IpRanges", []) if r.get("CidrIp") == "0.0.0.0/0"
    ] + [r.get("CidrIpv6", "") for r in rule.get("Ipv6Ranges", []) if r.get("CidrIpv6") == "::/0"]

    if not public_cidrs:
        return []

    protocol: str = rule.get("IpProtocol", "")
    from_port: int = rule.get("FromPort", 0)
    to_port: int = rule.get("ToPort", 65535)

    # All-traffic rule
    if protocol == "-1":
        return [
            {
                "port": "all",
                "protocol": "all",
                "cidr": public_cidrs[0],
                "port_name": "All Traffic",
                "severity": "CRITICAL",
                "notional_monthly_usd": 300.0,
            }
        ]

    matched: list[dict[str, Any]] = []
    for port, name in _CRITICAL_PORTS.items():
        if from_port <= port <= to_port:
            matched.append(
                {
                    "port": port,
                    "protocol": protocol,
                    "cidr": public_cidrs[0],
                    "port_name": name,
                    "severity": "CRITICAL",
                    "notional_monthly_usd": 300.0,
                }
            )
    for port, name in _HIGH_PORTS.items():
        if from_port <= port <= to_port and port not in _CRITICAL_PORTS:
            matched.append(
                {
                    "port": port,
                    "protocol": protocol,
                    "cidr": public_cidrs[0],
                    "port_name": name,
                    "severity": "HIGH",
                    "notional_monthly_usd": 100.0,
                }
            )
    return matched


def list_iam_credential_issues(
    region: str = "us-east-1",  # noqa: ARG001 — kept for registry interface consistency
) -> dict[str, Any]:
    """Audit IAM credential hygiene across the account.

    Checks: root MFA disabled, root access key exists, users without MFA,
    and access keys older than _ACCESS_KEY_MAX_AGE_DAYS days.

    The ``region`` parameter is accepted for interface consistency but is
    always ignored — IAM is a global service queried via us-east-1.

    Args:
        region: Ignored. Kept for uniform tool signature across the registry.

    Returns:
        Dict with ``root_mfa_enabled``, ``root_access_key_exists``,
        ``users_without_mfa``, ``stale_access_keys``, and ``issues`` list.
    """
    iam = get_client("iam", _IAM_REGION)

    summary = iam.get_account_summary()
    summary_map: dict[str, int] = summary.get("SummaryMap", {})
    root_mfa_enabled: bool = summary_map.get("AccountMFAEnabled", 0) == 1
    root_access_key_exists: bool = summary_map.get("AccountAccessKeysPresent", 0) > 0

    # Generate and fetch credential report
    for _ in range(_CREDENTIAL_REPORT_MAX_ATTEMPTS):
        gen_response = iam.generate_credential_report()
        if gen_response.get("State") == "COMPLETE":
            break
        time.sleep(_CREDENTIAL_REPORT_POLL_SLEEP)

    report_response = iam.get_credential_report()
    report_content: str = report_response["Content"].decode("utf-8")

    users_without_mfa: list[dict[str, str]] = []
    stale_access_keys: list[dict[str, Any]] = []
    cutoff = datetime.now(UTC) - timedelta(days=_ACCESS_KEY_MAX_AGE_DAYS)

    reader = csv.DictReader(io.StringIO(report_content))
    for row in reader:
        username: str = row.get("user", "")
        if username == "<root_account>":
            continue

        if row.get("mfa_active", "false").lower() == "false":
            users_without_mfa.append(
                {"username": username, "password_last_used": row.get("password_last_used", "")}
            )

        for key_idx in (1, 2):
            active_col = f"access_key_{key_idx}_active"
            rotated_col = f"access_key_{key_idx}_last_rotated"
            if row.get(active_col, "false").lower() != "true":
                continue
            rotated_str: str = row.get(rotated_col, "N/A")
            if rotated_str in ("N/A", ""):
                continue
            try:
                rotated_dt = datetime.fromisoformat(rotated_str.rstrip("Z").replace("+00:00", ""))
                rotated_dt = rotated_dt.replace(tzinfo=UTC)
            except ValueError:
                continue
            if rotated_dt < cutoff:
                age_days = (datetime.now(UTC) - rotated_dt).days
                stale_access_keys.append(
                    {"username": username, "key_index": key_idx, "age_days": age_days}
                )

    issues: list[dict[str, Any]] = []
    if not root_mfa_enabled:
        issues.append(
            {
                "issue_type": "root_mfa_disabled",
                "resource_id": "root",
                "severity": "CRITICAL",
                "detail": "Root account MFA is not enabled",
                "notional_monthly_usd": 500.0,
            }
        )
    if root_access_key_exists:
        issues.append(
            {
                "issue_type": "root_access_key_exists",
                "resource_id": "root",
                "severity": "CRITICAL",
                "detail": "Root account has active access keys — should be deleted",
                "notional_monthly_usd": 500.0,
            }
        )
    for user in users_without_mfa:
        issues.append(
            {
                "issue_type": "user_mfa_disabled",
                "resource_id": user["username"],
                "severity": "HIGH",
                "detail": f"IAM user {user['username']} does not have MFA enabled",
                "notional_monthly_usd": 50.0,
            }
        )
    for key in stale_access_keys:
        issues.append(
            {
                "issue_type": "access_key_too_old",
                "resource_id": key["username"],
                "severity": "MEDIUM",
                "detail": (
                    f"Access key {key['key_index']} for {key['username']} "
                    f"is {key['age_days']} days old (threshold: {_ACCESS_KEY_MAX_AGE_DAYS})"
                ),
                "notional_monthly_usd": 30.0,
            }
        )

    logger.info(
        "list_iam_credential_issues_complete",
        issues_count=len(issues),
        users_without_mfa=len(users_without_mfa),
        stale_keys=len(stale_access_keys),
    )
    return {
        "root_mfa_enabled": root_mfa_enabled,
        "root_access_key_exists": root_access_key_exists,
        "users_without_mfa": users_without_mfa,
        "stale_access_keys": stale_access_keys,
        "issues": issues,
    }
