# Architecture

Navidrome Statistic is a single-process FastAPI application with background collectors, an in-memory playback session tracker, a local SQLite database, and a static dashboard.

## Data flow

1. On startup, the application initializes and migrates SQLite.
2. A collector is created for each enabled Navidrome server. When the server list is empty, a compatible fallback connection is resolved field by field from non-empty `NAVIDROME_*` environment variables and previously saved fallback values, in that order. Once any server entry exists, only enabled entries from that list are collected; disabled entries do not reactivate the fallback.
3. Each collector calls the Subsonic `getNowPlaying` endpoint on a fixed interval. It also checks `getOpenSubsonicExtensions` for the `playbackReport` capability.
4. A `PlaybackSessionTracker` keeps active sessions in memory, keyed by player ID.
5. Counted sessions and below-threshold attempts are written to SQLite through the stats service, which also invalidates the dashboard snapshot cache on every write.
6. The statistics API aggregates stored data, and the dashboard renders the results with locally bundled Tailwind CSS and Apache ECharts assets.

The implementation is split along its natural seams:

| Component | Files |
| --- | --- |
| Application assembly: middleware, static pages, lifespan | `src/main.py` |
| Polling collectors, tracker registry, readiness report | `src/collectors.py`, `src/collector_manager.py` |
| Retention background maintenance | `src/retention.py` |
| Write paths, cache invalidation, cached snapshot builds | `src/stats_service.py` |
| HTTP routes: system/auth, statistics, privacy, connections | `src/routes/*.py` |
| Playback session tracking | `src/sessions.py` |
| History importers: event normalization, playlist bridge, `getSongHistory` seam | `src/importers/*.py` |
| SQLite schema, migrations, shared metadata store | `src/schema.py` |
| Local-time windows and SQL predicate composition | `src/windows.py` |
| Durable playback writes | `src/persistence.py` |
| Statistics read queries | `src/stats_queries.py` |
| Year-in-review aggregation | `src/review_queries.py` |
| Server registry CRUD with credential encryption | `src/server_registry.py`, `src/secretbox.py` |
| Retention, export, import, and deletion | `src/privacy_ops.py` |
| Dashboard and settings UI | `src/static/`, `src/static/js/` |

## Playback accounting

A session starts when an active `getNowPlaying` entry with a player ID is first observed. Repeated observations of the same track on the same player add active elapsed time. Paused or missing observations do not add listening time, and switching tracks finalizes the previous session.

Once active time reaches `PLAY_THRESHOLD_SEC`, the session is stored as one counted play. The same random session ID is used for periodic checkpoints and finalization, so a long session updates one row instead of adding duplicate plays. Sessions that end below the threshold are stored separately as playback attempts.

When the upstream server advertises the OpenSubsonic `playbackReport` extension, position, state, and playback-rate fields improve duration accounting: `playing` and `starting` advance listening time, `paused` keeps the session in the pause grace window, and the terminal `stopped` and `expired` states finalize the session immediately. Otherwise the tracker estimates duration from polling intervals.

Active sessions exist only in application memory; they are exposed to routes through a small behavioral surface (`now_playing()`, `active_count()`) rather than raw state. Counted sessions have durable checkpoints, but a process exit can still lose an uncommitted below-threshold session.

## History importers

Two optional importers fill the gap before live polling started. Both emit the same normalized listen event (provenance columns, unknown duration left NULL, `duration_confidence` set to `estimated`) and write through a single idempotent path: `StatsService.record_imported_events` inserts with an `external_event_key`, whose partial unique index makes re-runs no-ops. Import rows use `source = 'backfill'` or `'song_history'`, and add plays without inflating listening minutes.

- **Backfill bridge**: each enabled server may point at a Navidrome smart playlist (`.nsp`). A watch task reads it through public `getPlaylist` on `BACKFILL_INTERVAL_SEC` and converts one estimated event per track from its last-played timestamp; only the newest play per track is exact, so older plays under `playCount` are never invented. A manual **sync** endpoint runs once immediately.
- **`getSongHistory` seam**: the adapter paginates the proposed OpenSubsonic endpoint (upstream Navidrome PR #5650, not merged). The polling loop already probes for it; when a server ever advertises it, a one-shot initial import runs automatically.

To avoid double counting, imports never land on or after live-poller coverage: events must predate the oldest `source = 'poller'` row of that source and username, minus a small safety margin (`BACKFILL_CUTOFF_MARGIN_SEC`).

## Storage

SQLite stores listening records, source information, retention settings, and any Navidrome credentials saved through the server list or compatible fallback API. Saved credentials are encrypted at rest with AES-256-GCM using a per-installation key file (`secret.key`, mode 0600) next to the database; startup migrations re-wrap legacy plaintext values once. Schema migrations run during startup; schema v11 adds the importer dedup key and the per-server backfill playlist reference. Connections use write-ahead logging, foreign-key checks, and a bounded busy timeout.

Dashboard history is read through aggregate queries. A short-lived in-process cache reduces repeated work for identical dashboard filters. The cache lives behind the stats service: every playback write, retention purge, user import or deletion, and server mutation invalidates it inside the service, so callers cannot forget.

Finite retention policies run during startup and in a periodic background task. Policy updates, background cleanup, and manual **Apply now** requests are serialized on the application's event loop; manual cleanup also verifies that the saved policy still matches the previewed policy.

## Frontend

The dashboard, settings, and API reference pages are plain ES modules served under a strict Content Security Policy with no inline scripts and no build step for application code.

| Module | Responsibility |
| --- | --- |
| `js/http.js` | `apiFetch` with same-origin credentials, abort detection, and 401 handling |
| `js/auth.js` | Login dialog controller: overlay visibility, `inert` background, focus trap |
| `js/prefs.js` | localStorage-backed display preferences with cross-tab sync |
| `js/i18n/` | Locale registry: one module per language under `js/i18n/locales/`, pages derive catalogs via `pageMessages(...)`; tests guard key parity |
| `js/format.js` | Pure formatting, query-string building, and range validation helpers |
| `js/filters.js` | Dashboard filter state persisted to shareable URL parameters |
| `js/listbox.js` | Shared popover listbox and panel controls (review year picker, recent-plays column menu) |
| `js/app-info.js` | Application metadata from `/api/about`; fills `[data-app-version]` elements |
| `js/charts.js` | ECharts theme tokens; charts re-color when the theme preference changes |

Pure frontend logic is covered by Node unit tests (`npm run test:unit`); page behavior is covered by Playwright end-to-end tests.

## Runtime boundaries

- One application instance can collect from multiple Navidrome servers.
- Run the application with one worker and one event loop. Multi-worker deployments are not supported.
- Multiple processes or replicas collecting the same sources are not supported and can double-count plays.
- The SQLite file must be on storage suitable for a single-host database; shared network filesystems are not supported.
- Authentication is optional. `STATS_API_TOKEN` protects dashboard data and application APIs when configured, but the application does not terminate TLS.
- Health endpoints report process, database, collector, and upstream state. They are not a replacement for deployment-level monitoring or backups.

FastAPI exposes the current HTTP schema at `/openapi.json` and a same-origin searchable reference at `/docs` (also served at `/redoc`) unless OpenAPI routes are disabled with `OPENAPI_ENABLED=false`.

Cross-release stability promises are recorded in the [compatibility policy](compat.md).
