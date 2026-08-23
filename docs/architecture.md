# Architecture

Navidrome Statistic is a single-process FastAPI application with background collectors, an in-memory playback session tracker, a local SQLite database, and a static dashboard.

## Data flow

1. On startup, the application initializes and migrates SQLite.
2. A collector is created for each enabled Navidrome server. When no server has been saved in the settings page, the `NAVIDROME_*` environment variables provide a compatible default connection.
3. Each collector calls the Subsonic `getNowPlaying` endpoint on a fixed interval. It also checks `getOpenSubsonicExtensions` for the `playbackReport` capability.
4. A `PlaybackSessionTracker` keeps active sessions in memory, keyed by player ID.
5. Counted sessions and below-threshold attempts are written to SQLite.
6. The statistics API aggregates stored data, and the dashboard renders the results with locally bundled Tailwind CSS and Apache ECharts assets.

The main implementation is split across:

| Component | Files |
| --- | --- |
| Application lifecycle and HTTP routes | `src/main.py` |
| Subsonic client | `src/client.py` |
| Collector lifecycle | `src/collector_manager.py` |
| Session tracking | `src/sessions.py` |
| SQLite schema and statistics queries | `src/database.py`, `src/sqlite.py` |
| Retention, export, import, and deletion | `src/privacy_ops.py` |
| Dashboard and settings UI | `src/static/` |

## Playback accounting

A session starts when an active `getNowPlaying` entry with a player ID is first observed. Repeated observations of the same track on the same player add active elapsed time. Paused or missing observations do not add listening time, and switching tracks finalizes the previous session.

Once active time reaches `PLAY_THRESHOLD_SEC`, the session is stored as one counted play. The same random session ID is used for periodic checkpoints and finalization, so a long session updates one row instead of adding duplicate plays. Sessions that end below the threshold are stored separately as playback attempts.

When the upstream server advertises the OpenSubsonic `playbackReport` extension, position, state, and playback-rate fields improve duration accounting. Otherwise the tracker estimates duration from polling intervals.

Active sessions exist only in application memory. Counted sessions have durable checkpoints, but a process exit can still lose an uncommitted below-threshold session.

## Storage

SQLite stores listening records, source information, retention settings, and any Navidrome credentials saved through the settings page. Schema migrations run during startup. Connections use write-ahead logging, foreign-key checks, and a bounded busy timeout.

Dashboard history is read through aggregate queries. A short-lived in-process cache reduces repeated work for identical dashboard filters and is invalidated after relevant writes.

## Runtime boundaries

- One application instance can collect from multiple Navidrome servers.
- Multiple processes or replicas collecting the same sources are not supported and can double-count plays.
- The SQLite file must be on storage suitable for a single-host database; shared network filesystems are not supported.
- Authentication is optional. `STATS_API_TOKEN` protects dashboard data and application APIs when configured, but the application does not terminate TLS.
- Health endpoints report process, database, collector, and upstream state. They are not a replacement for deployment-level monitoring or backups.

FastAPI exposes the current HTTP schema at `/openapi.json` and interactive documentation at `/docs` unless OpenAPI routes are disabled with `OPENAPI_ENABLED=false`.
