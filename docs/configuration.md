# Configuration reference

[简体中文](configuration.zh-CN.md) · [Documentation](README.md)

This page lists application environment variables. With Docker Compose, declare them in the service’s `environment` or `env_file`; adding a value to the interpolation `.env` file alone does not pass it into the container.

| Variable | Default | Description |
| --- | --- | --- |
| `NAVIDROME_URL` | None | Fallback Navidrome base URL; used only while the saved server list is empty. |
| `NAVIDROME_USER` | None | Username for the fallback Subsonic connection. |
| `NAVIDROME_PASS` | None | Password for the fallback Subsonic connection. |
| `DATABASE_URL` | `.data/navidrome_stats.db` | SQLite file path for new local checkouts; an existing root-level `navidrome_stats.db` is still detected. Docker Compose sets `/data/navidrome_stats.db`. Despite the name, this is not a general database URL. |
| `STATS_API_TOKEN` | Empty | Protects dashboard data, application APIs, and OpenAPI routes when set. |
| `STATS_READ_ONLY_TOKEN` | Empty | Enables a viewer credential that can read dashboard/review data but cannot open settings or call administrative APIs. It must differ from every other configured token. |
| `STATS_READ_ONLY_SOURCE_ID` | Empty | Optional backend-enforced server scope for viewer sessions. |
| `STATS_READ_ONLY_USERNAME` | Empty | Optional backend-enforced username scope for viewer sessions. |
| `STATS_METRICS_AUTH` | `false` | Requires administrator authentication for `/metrics` when enabled. |
| `STATS_QUERY_BUDGET_MS` | `250` | Per-section Dashboard query budget used by `/metrics`, limited to 10–60000 ms. It tracks performance regressions; it does not enable rollups. |
| `COVER_ART_RESPONSE_MAX_BYTES` | `10485760` | Maximum upstream cover-art response accepted by the proxy, limited to 65536–67108864 bytes. |
| `OPENAPI_ENABLED` | `true` | Set to `false` to remove `/docs`, `/redoc`, and `/openapi.json`. |
| `POLL_INTERVAL` | `10` | Poll interval in seconds, limited to 5–300. |
| `PLAY_THRESHOLD_SEC` | `30` | Active playback seconds required to count a play, limited to 1–3600. |
| `MAX_INFERRED_INTERVAL_SEC` | `30` | Largest interval between successful active observations that may count as continuous listening, limited to 1–3600 seconds. The effective value is at least twice `POLL_INTERVAL` to tolerate normal request timing. Longer unobserved gaps add no duration and mark the saved total as a lower bound. |
| `PAUSE_GRACE_SEC` | `30` | Seconds to retain a paused or missing session, limited to 0–3600. |
| `CHECKPOINT_INTERVAL_SEC` | `60` | Refresh interval for durable active-session checkpoints, limited to 10–3600 seconds. |
| `SAVE_RETRY_ATTEMPTS` | `3` | Database save attempts for a session, limited to 1–10. |
| `MAX_POLL_BACKOFF_SEC` | `60` | Maximum upstream failure backoff, limited to 1–3600 seconds. |
| `BACKFILL_INTERVAL_SEC` | `3600` | How often a configured smart-playlist backfill is re-checked, limited to 300–86400 seconds. |
| `BACKFILL_CUTOFF_MARGIN_SEC` | `60` | Safety margin subtracted from live-poller coverage before importing, limited to 0–3600 seconds. |
| `RETENTION_MAINTENANCE_SEC` | `86400` | Automatic retention cleanup interval, limited to 60–604800 seconds. |
| `SESSION_COOKIE_SECURE` | `false` | Marks the login cookie Secure; enable it when users access the service through HTTPS. |
| `LISTENBRAINZ_INGEST_TOKEN` | Empty | Enables the ListenBrainz-compatible receiver when set together with `LISTENBRAINZ_INGEST_USERNAME`. It must differ from the administrator and viewer tokens. |
| `LISTENBRAINZ_INGEST_USERNAME` | Empty | Username assigned to listens accepted by the receiver. |
| `LISTENBRAINZ_INGEST_SOURCE_ID` | `listenbrainz` | Stable source identity used for receiver records and deduplication. |
| `LISTENBRAINZ_INGEST_SOURCE_NAME` | `ListenBrainz receiver` | Display name for receiver records. |

Environment variables are parsed when the application starts. The application refuses to start if administrator, viewer, or ingestion tokens share a value. Restart the container after changing them.
