"""A redacted collection status independent of cached statistics responses."""

from datetime import datetime, timezone

from src.config import env_int
from src.listenbrainz_ingest import load_ingest_config
from src.runtime_state import runtime_state
from src.server_registry import list_servers
from src.source_config import has_full_config, resolve_effective_source_config


async def collection_status(source_id: str | None = None) -> dict:
    servers = await list_servers()
    if not servers and has_full_config(await resolve_effective_source_config()):
        servers = [{"id": "legacy", "enabled": True}]
    servers = [server for server in servers if not source_id or server["id"] == source_id]
    enabled = [server for server in servers if server["enabled"]]
    receiver = load_ingest_config()
    receiver_enabled = receiver is not None and (not source_id or source_id == receiver.source_id)
    now = datetime.now(timezone.utc)
    stale_after = max(60, 3 * env_int("POLL_INTERVAL", default=10, min_value=5, max_value=300))
    states = [runtime_state.collector_snapshot(server["id"]) for server in enabled]
    healthy = [
        state["status"] == "running"
        and state["last_success_at"] is not None
        and (now - state["last_success_at"]).total_seconds() <= stale_after
        and runtime_state.collectors[server["id"]].last_save_ok is not False
        for server, state in zip(enabled, states)
    ]
    if states:
        if all(healthy):
            status = "live"
        elif all(state["status"] == "starting" for state in states):
            status = "starting"
        else:
            status = "degraded"
    elif receiver_enabled:
        status = "receiver_enabled"
    else:
        status = "disabled" if servers else "unconfigured"
    return {"status": status, "mixed_collection": bool(enabled and receiver_enabled)}
