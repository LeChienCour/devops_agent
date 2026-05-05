"""MCP server for security posture tools — standalone wrapper for demo/CLI use.

Architecture (ADR-001): All business logic lives in agent/tools/security.py.
This server re-exposes those functions over the MCP protocol for use with
``mcp dev`` or ``mcp-cli`` during live demos. The LangGraph agent NEVER calls
this server at runtime.

Usage:
    mcp dev src/mcp_servers/security/server.py
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from agent.tools import security

mcp = FastMCP("finops-security")


@mcp.tool()
def list_guardduty_findings(
    min_severity_score: float = 4.0,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """List active GuardDuty threat findings at or above a minimum severity score.

    Returns HIGH and CRITICAL findings with threat type, resource affected, and
    severity score. Returns an empty list with a warning if GuardDuty is not enabled.

    Args:
        min_severity_score: Minimum GuardDuty severity score (1.0–10.0). Defaults to 4.0.
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        Dict with findings list and detectors_checked count.
    """
    return security.list_guardduty_findings(min_severity_score, region)


@mcp.tool()
def list_config_noncompliant_rules(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """List AWS Config rules that have NON_COMPLIANT resources.

    Each non-compliant rule indicates a policy violation that may represent
    a security or compliance gap. Returns an empty list with a warning if
    AWS Config is not enabled.

    Args:
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        Dict with rules list. Each entry contains rule_name and noncompliant_resource_count.
    """
    return security.list_config_noncompliant_rules(region)


@mcp.tool()
def list_iam_analyzer_findings(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """List IAM Access Analyzer findings for external access to account resources.

    External access findings indicate S3 buckets, IAM roles, KMS keys, or other
    resources that grant access to principals outside the account.

    Args:
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        Dict with findings list and analyzers_checked count.
    """
    return security.list_iam_analyzer_findings(region)


@mcp.tool()
def list_security_hub_findings(
    min_severity: str = "HIGH",
    region: str = "us-east-1",
) -> dict[str, Any]:
    """List aggregated Security Hub findings at or above the minimum severity.

    Security Hub aggregates findings from GuardDuty, Inspector, Macie, and
    third-party integrations. Returns an empty list with a warning if
    Security Hub is not enabled.

    Args:
        min_severity: Minimum severity label (INFORMATIONAL/LOW/MEDIUM/HIGH/CRITICAL).
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        Dict with findings list (capped at 100) and total_returned count.
    """
    return security.list_security_hub_findings(min_severity, region)


@mcp.tool()
def get_cloudtrail_status(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Return CloudTrail trail configuration and identify logging gaps.

    Checks which trails are enabled, whether multi-region logging is active,
    and whether log file validation is enabled.

    Args:
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        Dict with trails list, has_multi_region_trail, region_logging_active,
        log_file_validation_enabled, and gaps list.
    """
    return security.get_cloudtrail_status(region)


@mcp.tool()
def list_open_security_groups(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """List EC2 security groups with public ingress on critical or high-risk ports.

    Flags rules that allow 0.0.0.0/0 or ::/0 on ports including SSH (22), RDP (3389),
    databases (MySQL, PostgreSQL, MSSQL, MongoDB, Redis), and other high-risk services.

    Args:
        region: AWS region to query. Defaults to us-east-1.

    Returns:
        Dict with security_groups list. Each entry contains group_id, group_name,
        open_rules, and max_severity.
    """
    return security.list_open_security_groups(region)


@mcp.tool()
def list_iam_credential_issues(
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Audit IAM credential hygiene across the account.

    Checks: root MFA disabled, root access key exists, IAM users without MFA,
    and access keys older than 90 days. IAM is global — region is ignored.

    Args:
        region: Ignored — IAM is a global service. Included for interface consistency.

    Returns:
        Dict with root_mfa_enabled, root_access_key_exists, users_without_mfa,
        stale_access_keys, and issues list.
    """
    return security.list_iam_credential_issues(region)


if __name__ == "__main__":
    mcp.run()
