"""Redacted connection probes and first-run diagnostic state."""

from __future__ import annotations

import ssl
from datetime import datetime, timezone
from typing import Any

import httpx

from src.privacy_ops import get_storage_stats
from src.runtime_state import runtime_state
from src.schemas import SUBSONIC_AUTH_ERROR_CODES
from src.server_registry import list_servers
from src.source_config import has_full_config, resolve_effective_source_config


def subsonic_error_code(data: Any) -> int | None:
    envelope = data.get("subsonic-response") if isinstance(data, dict) else None
    error = envelope.get("error") if isinstance(envelope, dict) else None
    raw = error.get("code") if isinstance(error, dict) else None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def classify_subsonic_response(data: Any) -> str:
    envelope = data.get("subsonic-response") if isinstance(data, dict) else None
    if not isinstance(envelope, dict):
        return "invalid_response"
    if envelope.get("status") == "ok":
        return "ok"
    code = subsonic_error_code(data)
    return "auth_failed" if code in SUBSONIC_AUTH_ERROR_CODES else "upstream_error"


def _cause_chain(exc: BaseException):
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def classify_connection_exception(exc: BaseException) -> str:
    if any(isinstance(cause, ssl.SSLError) for cause in _cause_chain(exc)):
        return "tls_error"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (401, 403):
            return "auth_failed"
        return "upstream_error"
    if isinstance(exc, httpx.ConnectError):
        return "network_unreachable"
    if isinstance(exc, (httpx.NetworkError, OSError)):
        return "network_unreachable"
    if isinstance(exc, httpx.ProtocolError):
        return "invalid_response"
    if isinstance(exc, (ValueError, TypeError)):
        return "invalid_response"
    return "unknown"


async def probe_connection(client) -> dict[str, Any]:
    """Probe one client without returning configuration or exception text."""
    try:
        data = await client.get_now_playing()
    except Exception as exc:
        return {"ok": False, "category": classify_connection_exception(exc)}
    category = classify_subsonic_response(data)
    return {
        "ok": category == "ok",
        "category": category,
        "upstream_code": subsonic_error_code(data),
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _diagnostic_category(
    *,
    configured: bool,
    enabled_count: int,
    history_records: int,
    snapshots: list[dict[str, Any]],
) -> str:
    if not configured:
        return "unconfigured"
    if enabled_count == 0:
        return "disabled"

    failures = [
        snapshot.get("last_error_category")
        for snapshot in snapshots
        if snapshot.get("last_poll_ok") is False
    ]
    for category in (
        "auth_failed",
        "tls_error",
        "timeout",
        "network_unreachable",
        "upstream_error",
        "invalid_response",
        "unknown",
    ):
        if category in failures:
            return category
    if any(
        snapshot.get("status") in {"degraded", "stopped", "not_running"}
        for snapshot in snapshots
    ):
        return "collector_degraded"
    if snapshots and all(snapshot.get("last_poll_ok") is True for snapshot in snapshots):
        return "connected_no_plays" if history_records == 0 else "ready"
    return "starting"


async def build_connection_diagnostics() -> dict[str, Any]:
    """Return a redacted aggregate suitable for authenticated settings UI."""
    servers = await list_servers()
    if servers:
        enabled = [server for server in servers if server.get("enabled", True)]
        source_ids = [server["id"] for server in enabled]
        configured = True
        configured_count = len(servers)
    else:
        fallback = await resolve_effective_source_config()
        configured = has_full_config(fallback)
        enabled = [fallback] if configured else []
        source_ids = ["legacy"] if configured else []
        configured_count = int(configured)

    storage = await get_storage_stats()
    snapshots = [runtime_state.collector_snapshot(source_id) for source_id in source_ids]
    now = datetime.now(timezone.utc)
    retry_values = [
        max(0, int((snapshot["retry_at"] - now).total_seconds()))
        for snapshot in snapshots
        if snapshot.get("retry_at") is not None
    ]
    successes = [
        snapshot["last_success_at"]
        for snapshot in snapshots
        if snapshot.get("last_success_at") is not None
    ]
    category = _diagnostic_category(
        configured=configured,
        enabled_count=len(enabled),
        history_records=storage["history_records"],
        snapshots=snapshots,
    )
    return {
        "schema_version": 1,
        "category": category,
        "configured_connection_count": configured_count,
        "enabled_connection_count": len(enabled),
        "history_record_count": storage["history_records"],
        "healthy_collector_count": sum(
            snapshot.get("status") == "running" for snapshot in snapshots
        ),
        "degraded_collector_count": sum(
            snapshot.get("status") in {"degraded", "stopped", "not_running"}
            for snapshot in snapshots
        ),
        "last_success_at": _iso(max(successes)) if successes else None,
        "retry_in_seconds": min(retry_values) if retry_values else None,
    }
