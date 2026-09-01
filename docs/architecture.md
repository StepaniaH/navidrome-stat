# Architecture

Navidrome Stat is a single-process FastAPI application with background collectors, an in-memory playback session tracker, a local SQLite database, and a static dashboard.

## Data flow

1. On startup, the application initializes and migrates SQLite.
2. A collector is created for each enabled Navidrome server. When the server list is empty, a compatible fallback connection is resolved field by field from non-empty `NAVIDROME_*` environment variables and previously saved fallback values, in that order. Once any server entry exists, only enabled entries from that list are collected; disabled entries do not reactivate the fallback.
3. Each collector calls the Subsonic `getNowPlaying` endpoint on a fixed interval. It also checks `getOpenSubsonicExtensions` for the `playbackReport` capability.
4. A `PlaybackSessionTracker` keeps active sessions in memory, keyed by player ID.
5. Counted sessions and below-threshold attempts are written to SQLite through the stats service, which requests dashboard-cache invalidation after every successful write. An invalidation failure is logged separately and does not turn a completed database write into a persistence failure.
6. The statistics API aggregates stored data, and the dashboard renders the results with locally bundled Tailwind CSS and Apache ECharts assets.

The implementation is organized by responsibility:

| Component | Files |
| --- | --- |
| Application assembly: middleware, static pages, lifespan | `src/main.py` |
| Polling collectors, tracker registry, readiness report | `src/collectors.py`, `src/collector_manager.py` |
| Redacted connection probes and aggregate diagnosis | `src/connection_diagnostics.py` |
| Retention background maintenance | `src/retention.py` |
| Write paths, cache invalidation, cached snapshot assembly | `src/stats_service.py` |
| Transactionally consistent dashboard reads | `src/stats_read_repository.py` |
| HTTP routes: system/auth, statistics, privacy, connections | `src/routes/*.py` |
| Playback session tracking | `src/sessions.py` |
| History importers: event normalization, playlist bridge, `getSongHistory` integration | `src/importers/*.py` |
| SQLite schema, migrations, shared metadata store | `src/schema.py` |
| Local-time windows and SQL predicate composition | `src/windows.py` |
| Durable playback writes | `src/persistence.py` |
| Statistics read queries by overview, timeline, ranking, and history | `src/stats_query_*.py`; `src/stats_queries.py` compatibility module |
| Year-in-review aggregation | `src/review_queries.py` |
| Server registry CRUD with credential encryption | `src/server_registry.py`, `src/secretbox.py` |
| Retention, versioned archives, and deletion | `src/privacy_retention.py`, `src/privacy_archive.py`, `src/privacy_deletion.py`; `src/privacy_ops.py` compatibility module |
| Dashboard and settings UI | `src/static/`, `src/static/js/` |

`src/database.py` continues to provide compatibility imports for existing callers. New core paths depend on the schema, persistence, query, and server-registry modules directly; it is not a transaction or repository layer.

## Playback accounting

A session starts when an active `getNowPlaying` entry with a player ID is first observed. Repeated observations of the same track on the same player add active elapsed time. Paused or missing observations do not add listening time, and switching tracks finalizes the previous session.

Once active time reaches `PLAY_THRESHOLD_SEC`, the session is stored as one counted play. The same random session ID is used for periodic checkpoints and finalization, so a long session updates one row instead of adding duplicate plays. Sessions that end below the threshold are stored separately as playback attempts.

When the upstream server advertises the OpenSubsonic `playbackReport` extension, position, state, and playback-rate fields improve duration accounting: `playing` and `starting` advance listening time, `paused` keeps the session in the pause grace window, and the terminal `stopped` and `expired` states finalize the session immediately. Client position reports may be less frequent than collector polls, so an unchanged position with an explicit playing state still advances by the observed wall-clock interval; seeks remain bounded to wall-clock time. Otherwise the tracker estimates duration from polling intervals.

Active sessions exist only in application memory; routes use the limited `now_playing()` and `active_count()` interface instead of accessing tracker state directly. Counted sessions have durable checkpoints, but a process exit can still lose an uncommitted below-threshold session.

## History importers

Two optional importers fill the gap before live polling started. Both emit the same normalized listen event (provenance columns, unknown duration left NULL, `duration_confidence` set to `estimated`) and write through a single idempotent path: `StatsService.record_imported_events` inserts with an `external_event_key`, whose partial unique index makes re-runs no-ops. Import rows use `source = 'backfill'` or `'song_history'`, and add plays without inflating listening minutes.

- **Backfill bridge**: each enabled server may point at a Navidrome smart playlist (`.nsp`). A watch task reads it through public `getPlaylist` on `BACKFILL_INTERVAL_SEC` and converts one estimated event per track from its last-played timestamp; only the newest play per track is exact, so older plays under `playCount` are never invented. A manual **sync** endpoint runs once immediately.
- **`getSongHistory` importer**: the adapter paginates the proposed OpenSubsonic endpoint (upstream Navidrome PR #5650, not merged). The polling loop already probes for it; when a server advertises it, the initial import commits one page at a time, persists its per-source/user offset in SQLite, resumes limited batches after restarts, and backs off after failures.

To avoid double counting, imports never land on or after live-poller coverage: events must predate the oldest `source = 'poller'` row of that source and username, minus a small safety margin (`BACKFILL_CUTOFF_MARGIN_SEC`).

## Storage

SQLite stores listening records, source information, retention settings, and any Navidrome credentials saved through the server list or compatible fallback API. New local checkouts place the database under `.data/`; when a root-level `navidrome_stats.db` already exists, the resolver keeps using it so an upgrade cannot silently present an empty installation. Docker Compose continues to set the explicit `/data/navidrome_stats.db` volume path. Saved credentials are encrypted at rest with AES-256-GCM using a per-installation key file (`secret.key`, mode 0600) next to the database; startup migrations re-wrap legacy plaintext values once. Schema migrations run during startup; schema v12 adds durable privacy-export record IDs and upstream album IDs, while schema v13 adds automatically maintained UTC epoch columns and finite-window indexes for history and playback attempts. An application whose supported schema is older than the stored version refuses startup before creating or altering schema objects and directs the operator to upgrade or restore a compatible backup. Connections use write-ahead logging, foreign-key checks, and a bounded busy timeout.

Privacy exports use format v3. Every history row and short-play attempt carries a stable record ID plus a canonical SHA-256 fingerprint, so repeated merge imports report inserted, skipped, and conflicting records instead of duplicating them. Import formats v1 and v2 remain readable and derive deterministic identities during import.

Album rankings use `(source, album_id)` when the upstream ID is present. Older rows fall back to `(source, album, artist)`, preventing common names such as “Live” or “Greatest Hits” from merging across artists or servers. A Navidrome ID resolved only for cover art is returned separately as `cover_art_id`; it never replaces the stored album identity used by detail queries.

Dashboard history is read through aggregate queries. A validated, immutable `StatsScope` is shared by cache identity and repository query conditions, so date, timezone, metric, server, and user selections stay consistent. Artist, album, and client detail queries reuse the same scope for totals, unique-track and per-play averages, local-date trends, top tracks, recent plays, and equal-length prior-period ranks; album identities include their source so same-named records cannot merge across servers. Detail duration values also carry a quality state: reported, polling estimate, lower bound, or unknown. Poller rows without a session ID predate durable checkpoint updates, and unfinished durable rows contain only their latest checkpoint, so both are lower bounds. Finalized poller rows remain estimates because existing history does not identify which collector version produced each row; this avoids claiming precision for playback-report records created before sparse reports were accounted for correctly. The relationship query uses that scope to return ranked time series, four local-time dayparts, and current/previous-period values for artists, albums, or clients. Its chart contract is documented in [Dashboard relationships and drill-downs](data-relations.md). `StatsReadRepository` runs detail and relationship reads inside one SQLite read transaction, while the local dashboard snapshot is assembled sequentially from one physical connection and database snapshot. Timestamp rows that require Python's IANA timezone and DST rules are streamed from SQLite instead of copied into another in-memory list. A short-lived in-process cache reduces repeated work for identical filters and relationship dimensions. The stats service requests invalidation after mutations; playback-cache errors are logged without misreporting a successful database write as a persistence failure. Below-threshold playback-attempt totals remain outside the main snapshot and are requested only when the Recent Plays accounting detail is opened. The request uses the same date, server, user, and timezone scope as the dashboard. Its rate compares below-threshold attempts with live-poller sessions and privacy-archive restores, excluding backfill and native-history imports that were not collected as live playback attempts.

Finite retention policies run during startup and in a periodic background task. Policy updates, background cleanup, and manual **Apply now** requests are serialized on the application's event loop; manual cleanup also verifies that the saved policy still matches the previewed policy.

Retention cleanup uses `DELETE`: removed pages become reusable inside SQLite, but the database file does not shrink automatically. Settings therefore show the current file size after cleanup and describe the estimated deleted record payload instead of claiming operating-system disk space will be released.

User deletion shares a mutation lock with live playback writes. It discards that user's in-memory sessions and suppresses already queued commits from those session IDs; a later playback observation creates a fresh session and is collected normally.

## Frontend

The dashboard, settings, and API reference pages are plain ES modules served under a strict Content Security Policy with no inline scripts and no build step for application code.

| Module | Responsibility |
| --- | --- |
| `js/http.js` | `apiFetch` with same-origin credentials, abort detection, and 401 handling |
| `js/auth.js` | Login dialog controller: overlay visibility, `inert` background, focus trap |
| `settings.css` | Settings layout and page-specific styling, kept out of HTML |
| `themes.css` | Shared semantic theme tokens for the dashboard, year-in-review, settings, and API reference |
| `js/themes.js` | Theme mode/palette registry, legacy preference compatibility, and pure appearance resolution |
| `js/theme-customization.js` | Validated browser-local preset overrides, contrast checks, and root custom-property application |
| `js/settings/appearance-settings.js` | Appearance picker and advanced-editor state, preview, import/export, and unsaved-change boundary |
| `js/settings/connection-settings.js` | Connection status, saved-server list, editor actions, and redacted diagnostic composition |
| `js/settings/privacy-settings.js` | Retention drafts, storage previews, user archives, and destructive-action lifecycle |
| `js/settings/connection-diagnostics.js` | Stable diagnostic-category presentation and first-use guidance |
| `theme-bootstrap.js` | Browser-local theme runtime, system color-scheme listener, root attributes, and cross-tab synchronization |
| `js/prefs.js` | Safe `localStorage` access for browser-local display preferences |
| `js/i18n/` | Locale registry: one module per language under `js/i18n/locales/`, pages derive catalogs via `pageMessages(...)`; tests guard key parity |
| `js/format.js` | Pure formatting, query-string building, and range validation helpers |
| `js/filters.js` | Dashboard filter state persisted to shareable URL parameters |
| `js/listbox.js` | Shared static and data-driven listbox interaction plus popover panel controls |
| `js/app-info.js` | Application metadata from `/api/about`; fills `[data-app-version]` elements |
| `js/charts.js` | ECharts theme tokens; charts re-color when the theme preference changes |
| `js/dashboard/now-playing.js` | Live request lifecycle, safe row rendering, and local elapsed-time ticker |
| `js/dashboard/history.js` | Recent-history rendering, column preferences, and first-use presentation |
| `js/dashboard/play-accounting.js` | Lazy counted/short-play explanation and scoped request lifecycle |
| `js/dashboard/historical-dashboard.js` | Summary, chart, ranking, and source-breakdown rendering |
| `js/dashboard/data-relations.js` | Scoped relationship query lifecycle and trend, daypart, and period-comparison charts |
| `js/dashboard/entity-detail.js` | URL-addressable artist/album details, in-page client details, scoped requests, and safe rendering |

Dashboard filters, the selected relationship dimension, artist and album identities, and year-in-review scope use shareable URL parameters. Opening an artist or album detail resolves the browser timezone token to an exact IANA name, preserves date, metric, server, and user scope, and restores through browser history. Client details preserve the same scope but remain page-local and use a POST body so the client name is not stored in the URL or query-string access logs. The dashboard carries the selected server, user, and resolved timezone into its review link; the review page restores those values together with the selected year, sends the same scope to the statistics API, and keeps the year, user, server, and timezone visible. Review requests expose explicit loading, empty, error, and retry states. Changing years aborts the previous request, and a generation check prevents an older response from replacing the current selection.

Appearance has two independent preferences. The mode is `system`, `dark`, or `light`; system mode resolves the browser's read-only `prefers-color-scheme` media query. The palette is one of Built-in, Gruvbox, Catppuccin, Solarized, Nord, Dracula, Tokyo Night, Macchiato, or Mocha. Every family provides a concrete light and dark variant, so the resolver always maps the pair directly to one of 18 theme IDs.

Every themed page loads `themes.css` and consumes the same resolved contract: `data-theme` names the concrete variant and `data-scheme` is `dark` or `light`. `theme-bootstrap.js` also exposes the selected mode and palette on the root element, applies validated custom overrides before emitting the theme-change event used for chart redraws, and updates system mode when the media query changes. Existing `navidrome-theme` values remain readable as a compatibility input. Mode, palette, and versioned per-theme color overrides stay in `localStorage` and are never sent to the server. The advanced editor changes six core semantic colors; invalid values and critical text/accent combinations below 4.5:1 contrast cannot be saved. Its import/export document contains exactly one concrete theme ID, a schema version, and the six validated colors; imports for another preset or with unknown fields are rejected.

`/api/diagnostics` is an authenticated adapter over saved-connection presence, collector runtime state, retry timing, and the aggregate history count. It returns stable categories and counts only: URLs, usernames, passwords, source IDs, upstream messages, and exception text remain behind the boundary. Public `/health/ready` retains its deployment-health role and does not gain listening-record counts.

Pure frontend logic is covered by Node unit tests (`npm run test:unit`); page behavior is covered by Playwright end-to-end tests.

Prometheus metrics cover poll/save health, dashboard build duration and cache outcomes, fixed-section query count/sum/max and budget violations, SQLite busy retries, import duration, and cover-art cache hits, misses, bytes in use, and configured limit. Query metrics use a fixed set of section labels and the `STATS_QUERY_BUDGET_MS` budget; they do not include user, server, track, or other high-cardinality values. Daily or hourly rollups remain deferred until production measurements and the multi-scale benchmark demonstrate that raw-history queries exceed their budgets.

Cover art is streamed from the upstream server with a size limit before it is cached. The proxy serves only bytes whose actual JPEG, PNG, GIF, WebP, or AVIF signature is recognized; an upstream header cannot override the detected type. Cache file reads, writes, scans, and eviction run in worker threads, and per-key request locks are removed after their final waiter exits.

## Runtime boundaries

- One application instance can collect from multiple Navidrome servers.
- Run the application with one worker and one event loop. Multi-worker deployments are not supported.
- Multiple processes or replicas collecting the same sources are not supported and can double-count plays.
- The SQLite file must be on storage suitable for a single-host database; shared network filesystems are not supported.
- Authentication is optional. `STATS_API_TOKEN` protects dashboard data and application APIs at one shared authorization level when configured; there are no separate viewer and administrator roles. The application does not terminate TLS.
- Health endpoints report process, database, collector, upstream, and durable-write state. A successful upstream poll cannot mask a failed playback write. These endpoints are not a replacement for deployment-level monitoring or backups.

FastAPI exposes the current HTTP schema at `/openapi.json` and a same-origin searchable reference at `/docs` (also served at `/redoc`) unless OpenAPI routes are disabled with `OPENAPI_ENABLED=false`.

Cross-release stability promises are recorded in the [compatibility policy](compat.md).
