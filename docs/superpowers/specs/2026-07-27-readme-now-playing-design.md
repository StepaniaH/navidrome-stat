# README and Now Playing Repair Design

## Scope

This change has two deliverables:

1. Replace the mixed-language root README with a concise English user guide, add a separate Chinese translation, and document a privacy-conscious Docker deployment.
2. Repair the now-playing data path after the multi-server polling change so the dashboard reports sessions from every running server tracker.

The change does not alter playback counting, the SQLite schema, authentication behavior, or the dashboard layout.

## Documentation Design

`README.md` is the canonical English README. A language link near the title points to `README.zh-CN.md`; the Chinese README links back to English. Each file uses one language throughout except for proper names, commands, environment variables, and API identifiers.

The English README is organized for operators rather than project maintainers:

1. Project purpose and important limitations.
2. Features.
3. Docker deployment using the published `stepaniah/navidrome-statistic` image.
4. Configuration reference.
5. Updating, health checks, logs, persistence, backup, and restore.
6. Security and privacy boundaries.
7. Build-from-source and local development instructions.
8. Project documentation and license.

The Chinese README mirrors the same facts and section order without mixing English prose into Chinese paragraphs. Release-maintainer instructions remain separate from the primary deployment path.

All examples use reserved domains and obvious placeholders. They do not include real server addresses, usernames, passwords, tokens, database records, log excerpts, or deployment-specific paths. The guide states that `.env` and SQLite files are sensitive, that the database stores listening metadata in plaintext, and that `STATS_API_TOKEN` or a trusted authentication boundary is required outside a trusted network.

The published-image Compose example uses a named volume to avoid host file ownership surprises with the non-root UID 1000 container. A source-build alternative points to the repository's existing `docker-compose.yml`. The documentation distinguishes application liveness (`/health`) from upstream availability and does not claim TLS, backup automation, reverse-proxy security, or public-internet readiness.

## Runtime Design

The regression was introduced when multi-server support changed lifespan startup from the global `session_tracker` to one local `PlaybackSessionTracker` per configured server. Polling updates those local trackers, but `/api/stats/now-playing`, readiness, and Prometheus metrics still inspect only the unused global tracker.

A module-level runtime tracker collection will become the single read surface for live sessions:

- The existing global `session_tracker` remains for direct `polling_loop()` compatibility and focused tests.
- Lifespan registers each per-server tracker in the runtime collection before starting its polling task.
- Lifespan removes registered trackers during shutdown after finalization.
- A small iterator/count helper reads a snapshot of the registered trackers. When no lifespan trackers are registered, it falls back to the global tracker so existing direct consumers keep working.
- `/api/stats/now-playing`, readiness, and `/metrics` use this shared read surface.

Now-playing includes only sessions whose `paused` flag is false. A paused or temporarily missing session remains in memory during `PAUSE_GRACE_SEC`, but it is not currently playing and therefore must not be displayed or counted as active. The API response schema remains unchanged: `username`, `title`, `artist`, `client_name`, and `seconds_elapsed`. Server identity is intentionally not added in this repair because that would expand the public interface and frontend scope.

`seconds_elapsed` remains wall-clock time since the session was first observed, matching the current API contract. This repair does not change it to active listening duration.

## Data Flow

1. Lifespan resolves enabled server configurations.
2. It creates and registers one tracker per valid server.
3. Each polling task writes current observations to its assigned tracker.
4. The now-playing endpoint snapshots every registered tracker, excludes paused sessions, and serializes active session metadata.
5. Readiness and Prometheus metrics count the same visible active sessions.
6. Shutdown cancels polling, finalizes each tracker, unregisters it, and closes each client.

No live metadata is persisted or logged by this registry. Existing database writes continue through each tracker's save callbacks.

## Error Handling

Malformed or absent upstream entries continue to follow the existing session tracker rules. The endpoint retains its generic 503 response if serialization fails and does not log session metadata. Registry cleanup runs during normal lifespan shutdown; startup failures leave no stale registered tracker from a partially constructed server.

## Testing

Regression tests use synthetic metadata only and cover:

- A lifespan-created per-server tracker becoming visible through `/api/stats/now-playing`.
- Sessions from multiple trackers being aggregated.
- Paused sessions being retained internally but excluded from now-playing and active-session metrics.
- Readiness and Prometheus metrics using the same aggregate count.
- Existing direct global-tracker tests remaining compatible.
- README language links, required deployment sections, placeholder-only examples, and local Markdown links.

Verification includes focused tests, the full test suite, Markdown link checking, `docker compose config`, `git diff --check`, final diff review, and a scan for accidentally added sensitive values. Docker image smoke testing is attempted only if a Docker daemon is available; otherwise it is reported as an environment blocker.

## Documentation Synchronization

The implementation updates `docs/current-state.md`, `docs/interfaces.md`, `docs/privacy.md` only where current facts or privacy guidance change. A new task in `docs/tasks.md` records scope, status, verification, and completion evidence in accordance with repository policy.

## Rollback

The runtime change is in-memory only and requires no data migration. Rollback restores the previous tracker read path and README files. Existing SQLite data is unaffected.
