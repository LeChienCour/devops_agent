"""Boto3 client factory — avoids re-creating clients on every call.

Clients are cached in a module-level dict keyed by ``service:region``.
This is safe for Lambda (single-process, single-thread per invocation).
"""

from __future__ import annotations

from typing import Any

import boto3

__all__ = ["get_client"]

_clients: dict[str, Any] = {}


def get_client(service: str, region: str = "us-east-1") -> Any:
    """Return a cached boto3 client for *service* in *region*.

    Args:
        service: AWS service name, e.g. ``"ce"``, ``"ssm"``, ``"dynamodb"``.
        region: AWS region identifier. Defaults to ``"us-east-1"``.

    Returns:
        A boto3 service client.  The same instance is returned on subsequent
        calls with the same arguments.
    """
    key = f"{service}:{region}"
    if key not in _clients:
        _clients[key] = boto3.client(service, region_name=region)
    return _clients[key]
