# Collector Hot Reload Design

## Scope

Server create, update, enable, disable, and delete operations must update live Navidrome polling without restarting the application. Existing playback counting, database schema, authentication, and public statistics response fields remain unchanged.

## Root Cause

FastAPI lifespan reads server configuration once and creates local client, tracker, and task lists. The server configuration endpoints only persist SQLite rows. They have no path to replace those runtime objects, so saved changes do not affect polling until the next process start.

## Runtime Ownership

A `CollectorManager` in `src/main.py` owns live collectors by server ID. Each collector contains one `NavidromeClient`, one `PlaybackSessionTracker`, and one polling task.

The manager provides these operations:

- `start(server)`: build and start an enabled, complete server configuration.
- `replace(server)`: construct the replacement first; then finalize the old tracker, cancel its task, close its client, and activate the replacement. A disabled server is handled as `stop(server_id)`.
- `stop(server_id)`: finalize existing sessions once, cancel and await the task, close the client, and remove the tracker from the now-playing registry.
- `stop_all()`: stop every collector during application shutdown.

The existing global `session_tracker` and `polling_loop(client)` remain for direct compatibility tests. Live statistics continue to aggregate `_runtime_trackers`, which the manager updates.

## API Behavior

After database persistence:

- `POST /api/servers` calls `replace()` and returns only after the collector is active.
- `PUT /api/servers/{server_id}` calls `replace()`; disabling stops that collector immediately.
- `DELETE /api/servers/{server_id}` stops the collector immediately after successful deletion.
- Legacy `PUT /api/source/config` hot-reloads the legacy collector only when no rows exist in the `servers` table. Environment variables retain priority over saved legacy values.

The replacement client is constructed before the old collector is stopped. Constructor failure leaves the old collector running. If database persistence succeeds but runtime activation fails, the endpoint returns generic HTTP 503 without credentials or upstream response data. The saved configuration remains authoritative and is retried by a later update or process restart; the API does not attempt a second credential-bearing database rollback.

Deletion stops the collector after the database row is removed. Stop errors are logged without server metadata and return generic HTTP 503; normal idempotent absence remains a 404.

## Session Semantics

Before a collector is stopped or replaced, `finalize_all()` applies existing thresholds to every in-memory session. Sessions at or above the threshold are saved once; below-threshold sessions follow the existing short-play behavior. No session is transferred between old and new credentials or server URLs.

## Concurrency

Manager mutations use one `asyncio.Lock`, serializing startup and configuration changes. Read paths snapshot `_runtime_trackers` as they do now. Polling tasks for unrelated servers remain active during a single-server replacement.

## User Interface

Settings copy states that server changes apply immediately. Environment variable documentation remains explicit: legacy environment values take precedence over legacy saved fallback values, but rows managed by the multi-server API are live-reloaded directly.

## Testing

Synthetic tests cover:

- Lifespan starts configured collectors through the manager and stops them on shutdown.
- Create starts a collector immediately.
- Update finalizes and closes the old collector before replacement becomes visible.
- Disable and delete stop only the selected collector.
- Replacement construction failure preserves the old collector and returns generic 503.
- Legacy source save reloads only when no multi-server rows exist.
- Settings no longer instruct users to restart.
- Full tests, links, diff checks, and privacy scans remain clean.

## Privacy

Tests use reserved domains and synthetic credentials. Manager logs contain lifecycle state and exception type/message only where existing policy permits; they never log server URLs, usernames, passwords, Subsonic tokens, response bodies, or playback metadata.

## Rollback

No migration is required. Rolling back restores lifespan-owned lists and restart-required behavior. SQLite server rows and playback history remain valid.
