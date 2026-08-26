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
| SQLite schema, migrations, shared metadata store | `src/schema.py` |
| Local-time windows and SQL predicate composition | `src/windows.py` |
| Durable playback writes | `src/persistence.py` |
| Statistics read queries | `src/stats_queries.py` |
| Server registry CRUD | `src/server_registry.py` |
| Retention, export, import, and deletion | `src/privacy_ops.py` |
| Dashboard and settings UI | `src/static/`, `src/static/js/` |

## Playback accounting

A session starts when an active `getNowPlaying` entry with a player ID is first observed. Repeated observations of the same track on the same player add active elapsed time. Paused or missing observations do not add listening time, and switching tracks finalizes the previous session.

Once active time reaches `PLAY_THRESHOLD_SEC`, the session is stored as one counted play. The same random session ID is used for periodic checkpoints and finalization, so a long session updates one row instead of adding duplicate plays. Sessions that end below the threshold are stored separately as playback attempts.

When the upstream server advertises the OpenSubsonic `playbackReport` extension, position, state, and playback-rate fields improve duration accounting. Otherwise the tracker estimates duration from polling intervals.

Active sessions exist only in application memory; they are exposed to routes through a small behavioral surface (`now_playing()`, `active_count()`) rather than raw state. Counted sessions have durable checkpoints, but a process exit can still lose an uncommitted below-threshold session.

## Storage

SQLite stores listening records, source information, retention settings, and any Navidrome credentials saved through the server list or compatible fallback API. Schema migrations run during startup. Connections use write-ahead logging, foreign-key checks, and a bounded busy timeout.

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
