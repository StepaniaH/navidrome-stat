# Collector Hot Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply Navidrome server configuration changes to live polling immediately without restarting the service.

**Architecture:** A module-level `CollectorManager` owns one client, tracker, and task per server ID and serializes mutations with an `asyncio.Lock`. API writes persist first and then call the manager; replacement constructs the new collector before finalizing and stopping the old one, while disabled or deleted servers are stopped immediately.

**Tech Stack:** Python 3.11, asyncio, FastAPI lifespan and routes, pytest/pytest-asyncio, static HTML/JavaScript.

## Global Constraints

- Never expose server URLs, usernames, passwords, tokens, response bodies, or playback metadata in logs or errors.
- Preserve playback threshold, short-play, now-playing, readiness, and metrics semantics.
- Preserve environment-variable priority for the legacy source.
- Do not change SQLite schema or public statistics response fields.
- Finalize old sessions before stopping or replacing a collector.
- Do not create a Git commit unless explicitly requested.

---

### Task 1: Specify Collector Lifecycle with Failing Tests

**Files:**
- Create: `tests/test_collector_manager.py`
- Modify: `tests/test_lifespan.py`

**Interfaces:**
- Produces desired `CollectorManager(client_factory, poller)` behavior.
- Expected methods: `start(server: dict)`, `replace(server: dict)`, `stop(server_id: str)`, `stop_all()`.
- Expected property: `collectors: dict[str, Collector]` where each collector exposes `client`, `tracker`, and `task`.

- [ ] Add tests with synthetic clients and a blocking async poller for start, replace, disable, stop, stop-all, replacement-construction failure, session finalization, task cancellation, and client closure.
- [ ] Update lifespan test expectations so startup delegates configured servers to the manager and shutdown leaves no collectors.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_collector_manager.py tests/test_lifespan.py` and verify failures are caused by the missing manager.

### Task 2: Implement CollectorManager and Lifespan Ownership

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_collector_manager.py`
- Test: `tests/test_lifespan.py`

**Interfaces:**
- `Collector` is a dataclass containing `client: NavidromeClient`, `tracker: PlaybackSessionTracker`, and `task: asyncio.Task`.
- `CollectorManager._build(server)` validates complete configuration, creates callback-bound tracker and client, and returns an unstarted `(client, tracker)` pair.
- `_runtime_trackers` remains the read registry used by `_active_sessions()`.

- [ ] Add `Collector`, `CollectorManager`, and module-level `collector_manager`.
- [ ] Implement start/replace/stop/stop-all under one lock, with internal unlocked helpers to avoid recursive lock acquisition.
- [ ] Make lifespan load initial server configs through `collector_manager.start()` and call `stop_all()` during shutdown.
- [ ] Keep the legacy `polling_loop(client)` compatibility path unchanged.
- [ ] Run focused tests and verify all pass.

### Task 3: Hot Reload Configuration APIs

**Files:**
- Modify: `tests/test_source_config.py`
- Create: `tests/test_server_api.py`
- Modify: `src/main.py`

**Interfaces:**
- Server POST/PUT call `collector_manager.replace(server)` after `save_server(server)`.
- Server DELETE calls `collector_manager.stop(server_id)` after `delete_server(server_id)`.
- Legacy source PUT calls `_reload_legacy_source_if_active()` after persistence only when `list_servers()` is empty.

- [ ] Add failing route tests asserting immediate manager calls for create/update/disable/delete, generic 503 on manager errors, and no sensitive response content.
- [ ] Add failing legacy source tests for reload when no multi-server rows exist and no reload when rows exist.
- [ ] Implement route calls and a generic `_apply_runtime_config` wrapper that logs no configuration fields and raises `HTTPException(503, "Saved configuration could not be applied")`.
- [ ] Run route and manager tests and verify all pass.

### Task 4: Update Settings and Interface Documentation

**Files:**
- Modify: `src/static/settings.html`
- Modify: `tests/test_static_settings.py`
- Modify: `docs/current-state.md`
- Modify: `docs/interfaces.md`
- Modify: `docs/privacy.md`
- Modify: `docs/tasks.md`

**Interfaces:**
- Settings success and description copy state that changes apply immediately.
- Environment copy explains legacy precedence without restart instructions.

- [ ] Add static tests rejecting restart-required wording and requiring immediate-apply wording in both languages.
- [ ] Update visible markup, translation maps, and fallback translation fragments.
- [ ] Document manager ownership, route hot reload, failure behavior, and non-sensitive logging.
- [ ] Run static tests and Markdown links.

### Task 5: Verify and Exercise the Local Service

**Files:**
- Verify all changed files.

**Interfaces:**
- Local service remains at `http://127.0.0.1:39421`.

- [ ] Run `.venv/bin/python -m pytest -q`.
- [ ] Run `.venv/bin/python scripts/check_md_links.py`, `git diff --check`, final diff review, and sensitive-value scans.
- [ ] Stop the existing local process and restart the new code in the background without printing configuration values.
- [ ] Verify redacted `/health/ready`, `/metrics`, and server counts; confirm poll success advances and no restart-required UI copy remains.
- [ ] Complete NDS-REL-002 with actual evidence and any environment blockers.
