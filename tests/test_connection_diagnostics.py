import ssl
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.connection_diagnostics import (
    _diagnostic_category,
    build_connection_diagnostics,
    classify_connection_exception,
    classify_subsonic_response,
    probe_connection,
)
from src.runtime_state import runtime_state


@pytest.mark.parametrize("code", [40, 41, 42, 43, 44, 50])
def test_response_classification_uses_stable_categories(code):
    assert classify_subsonic_response({"subsonic-response": {"status": "ok"}}) == "ok"
    assert classify_subsonic_response({
        "subsonic-response": {"status": "failed", "error": {"code": code}}
    }) == "auth_failed"
    assert classify_subsonic_response({"unexpected": True}) == "invalid_response"


def test_exception_classification_distinguishes_transport_failures():
    request = httpx.Request("GET", "https://example.invalid")
    assert classify_connection_exception(httpx.ReadTimeout("slow", request=request)) == "timeout"
    assert classify_connection_exception(ssl.SSLError("certificate verify failed")) == "tls_error"
    tls = httpx.ConnectError("tls", request=request)
    tls.__cause__ = ssl.SSLError("certificate verify failed")
    assert classify_connection_exception(tls) == "tls_error"
    assert (
        classify_connection_exception(httpx.RemoteProtocolError("bad frame", request=request))
        == "invalid_response"
    )
    assert classify_connection_exception(ConnectionError("offline")) == "network_unreachable"


@pytest.mark.parametrize(
    ("enabled_count", "history_records", "snapshots", "expected"),
    [
        (0, 0, [], "disabled"),
        (1, 0, [{"status": "starting", "last_poll_ok": None}], "starting"),
        (1, 0, [{"status": "running", "last_poll_ok": True}], "connected_no_plays"),
        (1, 4, [{"status": "running", "last_poll_ok": True}], "ready"),
        (1, 4, [{"status": "stopped", "last_poll_ok": None}], "collector_degraded"),
        (
            1,
            4,
            [{"status": "degraded", "last_poll_ok": False, "last_error_category": "timeout"}],
            "timeout",
        ),
    ],
)
def test_aggregate_category_prioritizes_actionable_runtime_state(
    enabled_count,
    history_records,
    snapshots,
    expected,
):
    assert _diagnostic_category(
        configured=True,
        enabled_count=enabled_count,
        history_records=history_records,
        snapshots=snapshots,
    ) == expected


@pytest.mark.asyncio
async def test_probe_never_returns_raw_exception_text():
    client = AsyncMock()
    client.get_now_playing.side_effect = RuntimeError("synthetic secret detail")
    result = await probe_connection(client)
    assert result == {"ok": False, "category": "unknown"}
    assert "synthetic" not in str(result)


@pytest.mark.asyncio
async def test_aggregate_diagnostics_reports_first_run_without_configuration():
    with patch("src.connection_diagnostics.list_servers", AsyncMock(return_value=[])):
        with patch(
            "src.connection_diagnostics.resolve_effective_source_config",
            AsyncMock(return_value={"url": None, "user": None, "password": None}),
        ):
            with patch(
                "src.connection_diagnostics.get_storage_stats",
                AsyncMock(return_value={"history_records": 0}),
            ):
                result = await build_connection_diagnostics()

    assert result["category"] == "unconfigured"
    assert result["enabled_connection_count"] == 0
    assert result["history_record_count"] == 0
    assert "url" not in result
    assert "username" not in result


@pytest.mark.asyncio
async def test_aggregate_diagnostics_reports_auth_failure_and_retry():
    runtime_state.reset()
    source_id = "server-1"
    now = datetime.now(timezone.utc)
    runtime_state.record_poll_upstream_error(now, 40, source_id)
    runtime_state.set_collector_retry(source_id, now + timedelta(seconds=30))
    collector = runtime_state._collector(source_id)
    collector.task = Mock()
    collector.task.done.return_value = False
    try:
        with patch(
            "src.connection_diagnostics.list_servers",
            AsyncMock(return_value=[{"id": source_id, "enabled": True}]),
        ):
            with patch(
                "src.connection_diagnostics.get_storage_stats",
                AsyncMock(return_value={"history_records": 12}),
            ):
                result = await build_connection_diagnostics()
    finally:
        runtime_state.reset()

    assert result["category"] == "auth_failed"
    assert 0 <= result["retry_in_seconds"] <= 30
    assert result["healthy_collector_count"] == 0
