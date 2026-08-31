<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/icon-dark.svg">
  <img src="assets/icon.svg" alt="Navidrome Stat" width="140">
</picture>

# Navidrome Stat

<a href="https://www.producthunt.com/products/navidrome-stat/launches/navidrome-stat?embed=true&amp;utm_source=badge-featured&amp;utm_medium=badge&amp;utm_campaign=badge-navidrome-stat" target="_blank" rel="noopener noreferrer"><picture><source media="(prefers-color-scheme: dark)" srcset="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1207528&amp;theme=dark&amp;t=1787616376509"><img alt="Navidrome Stat - A self-hosted service track and display your Navidrome usage | Product Hunt" width="250" height="54" src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1207528&amp;theme=light&amp;t=1787616376509"></picture></a>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Hub](https://img.shields.io/docker/v/stepaniah/navidrome-statistic/latest?label=Docker&logo=docker&logoColor=white)](https://hub.docker.com/r/stepaniah/navidrome-statistic)
[![Docker Pulls](https://img.shields.io/docker/pulls/stepaniah/navidrome-statistic?logo=docker&logoColor=white)](https://hub.docker.com/r/stepaniah/navidrome-statistic)

<img src="assets/screenshots/dashboard-frappe-top.png" alt="Playback statistics dashboard with now playing, totals, client and transcoding charts" width="920">

</div>

[简体中文](README.zh-CN.md) · [Product Hunt](https://www.producthunt.com/products/navidrome-stat)

Navidrome Stat collects playback activity reported by Navidrome and presents it in one dashboard. It provides a consistent view across Subsonic-compatible clients, browsers, phones, computers, and multiple Navidrome servers without requiring every client to implement its own statistics.

The service polls `getNowPlaying`, tracks listening sessions in memory, stores results in SQLite, and serves a self-contained web interface.

## Features

- Aggregates current and historical playback across clients, devices, users, and Navidrome servers.
- Shows listening time, play history, hourly and daily trends, a weekday × hour heatmap, client usage, transcoding, and artist, album, or track rankings.
- A year-in-review page with totals, listening streaks, monthly and time-of-day charts, top lists, and URL-persisted year, server, user, and timezone scope.
- Cover art for history, rankings, and now playing through a cached, authenticated proxy.
- System, dark, and light appearance modes combine with nine palette families and 18 concrete variants, with a matching light and dark treatment for every family. Advanced settings can locally adjust six core colors of each preset with live preview, grouped contrast validation, HEX copy, unsaved-change protection, and strict per-preset JSON import or export. Appearance choices stay in the browser and apply across the dashboard, year-in-review, settings, and API reference; seven interface languages are available.
- Dashboard filters and year-in-review scope persist in the URL, so views survive reloads and can be shared as links.
- The recent-plays table has configurable column visibility on desktop and mobile, saved per browser, plus on-demand details about sessions that ended before they counted as plays.
- Uses configurable play and pause thresholds, durable session checkpoints, and OpenSubsonic playback progress when available.
- Supports per-server filtering, connection management with first-use guidance and redacted failure diagnosis, retention settings, and per-user JSON export, import, and deletion.
- Filter the dashboard and year-in-review by user as well as server; the review charts switch between play counts and listening time.
- Offers optional token authentication for dashboard data and APIs.
- Serves pinned frontend assets locally and runs as a non-root user in the published container.

## Screenshots

| | |
| --- | --- |
| <img src="assets/screenshots/dashboard-frappe-charts.png" alt="Hourly, daily, and weekday-by-hour charts"> | <img src="assets/screenshots/dashboard-frappe-rankings.png" alt="Top artists and albums, server sources, recent plays"> |
| <img src="assets/screenshots/dashboard-gruvbox.png" alt="The same dashboard in the Gruvbox theme"> | |

## Important limitations

- Run a single Navidrome Stat instance for a set of sources. Multiple instances polling the same sources can double-count plays.
- Active sessions are held in one process. Multi-worker Uvicorn deployments are not supported.
- Listening records in SQLite are stored unencrypted; saved server credentials are encrypted at rest with a local key file (`secret.key`) that is not a defense against a fully compromised host.
- The application does not provide TLS. Use a trusted network or an HTTPS reverse proxy for remote access.

## Docker deployment

### Requirements

- Docker Engine with Docker Compose v2
- Network access from the container to each Navidrome server
- A Navidrome account that can call the Subsonic API

### 1. Create a deployment directory

```bash
mkdir navidrome-stat
cd navidrome-stat
```

### 2. Create `.env`

Use a long, random value for `STATS_API_TOKEN`. Do not commit this file or include it in support logs.

```dotenv
NAVIDROME_URL=https://navidrome.example.invalid
NAVIDROME_USER=example_user
NAVIDROME_PASS=<navidrome-password>
STATS_API_TOKEN=<long-random-token>

POLL_INTERVAL=10
PLAY_THRESHOLD_SEC=30
PAUSE_GRACE_SEC=30
```

The three `NAVIDROME_*` variables provide one fallback connection when no server entries have been saved. For this fallback, each non-empty environment value takes precedence over the corresponding value already stored in SQLite. Once any entry exists under **Settings > Connections**, only enabled entries from that list are collected; the fallback is not used, even when every saved entry is disabled.

To aggregate multiple servers, add each connection from **Settings > Connections** after startup. Credentials saved there are encrypted at rest with a per-installation key file (`secret.key`) generated beside the SQLite database. Back up that file together with the database, or plan to re-enter passwords after restoring a database-only copy; the encryption protects database copies and backups from casual inspection, not a fully compromised host. If that storage model is unsuitable, use only the single environment-configured connection and do not save connections through the settings page.

### 3. Create `compose.yaml`

Use a specific version tag instead of `latest` when you want reproducible deployments.

```yaml
services:
  navidrome-stat:
    image: stepaniah/navidrome-statistic:latest
    container_name: navidrome-stat
    user: "1000:1000"
    ports:
      - "39421:39421"
    volumes:
      - navidrome-stat-data:/data
    environment:
      NAVIDROME_URL: ${NAVIDROME_URL}
      NAVIDROME_USER: ${NAVIDROME_USER}
      NAVIDROME_PASS: ${NAVIDROME_PASS}
      STATS_API_TOKEN: ${STATS_API_TOKEN}
      DATABASE_URL: /data/navidrome_stats.db
      POLL_INTERVAL: ${POLL_INTERVAL:-10}
      PLAY_THRESHOLD_SEC: ${PLAY_THRESHOLD_SEC:-30}
      PAUSE_GRACE_SEC: ${PAUSE_GRACE_SEC:-30}
      CHECKPOINT_INTERVAL_SEC: ${CHECKPOINT_INTERVAL_SEC:-60}
      SAVE_RETRY_ATTEMPTS: ${SAVE_RETRY_ATTEMPTS:-3}
      MAX_POLL_BACKOFF_SEC: ${MAX_POLL_BACKOFF_SEC:-60}
      RETENTION_MAINTENANCE_SEC: ${RETENTION_MAINTENANCE_SEC:-86400}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-false}
      STATS_METRICS_AUTH: ${STATS_METRICS_AUTH:-false}
      OPENAPI_ENABLED: ${OPENAPI_ENABLED:-true}
    restart: unless-stopped
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:39421/health')"
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

volumes:
  navidrome-stat-data:
```

### 4. Start the service

```bash
docker compose up -d
docker compose ps
```

Open `http://localhost:39421`. When `STATS_API_TOKEN` is configured, enter it in the login screen; the browser stores an HttpOnly session cookie rather than the token itself.

`/health` reports process liveness. `/health/ready` also checks the database, collectors, upstream polling, and durable playback writes. An upstream or database failure can therefore make readiness degraded or not ready while the process remains healthy.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `NAVIDROME_URL` | None | Fallback Navidrome base URL; used only while the saved server list is empty. |
| `NAVIDROME_USER` | None | Username for the fallback Subsonic connection. |
| `NAVIDROME_PASS` | None | Password for the fallback Subsonic connection. |
| `DATABASE_URL` | `.data/navidrome_stats.db` | SQLite file path for new local checkouts; an existing root-level `navidrome_stats.db` is still detected. Docker Compose sets `/data/navidrome_stats.db`. Despite the name, this is not a general database URL. |
| `STATS_API_TOKEN` | Empty | Protects dashboard data, application APIs, and OpenAPI routes when set. |
| `STATS_METRICS_AUTH` | `false` | Requires authentication for `/metrics` when both this option and `STATS_API_TOKEN` are set. |
| `STATS_QUERY_BUDGET_MS` | `250` | Per-section Dashboard query budget used by `/metrics`, limited to 10–60000 ms. It observes regressions; it does not enable rollups. |
| `COVER_ART_RESPONSE_MAX_BYTES` | `10485760` | Maximum upstream cover-art response accepted by the proxy, limited to 65536–67108864 bytes. |
| `OPENAPI_ENABLED` | `true` | Set to `false` to remove `/docs`, `/redoc`, and `/openapi.json`. |
| `POLL_INTERVAL` | `10` | Poll interval in seconds, limited to 5–300. |
| `PLAY_THRESHOLD_SEC` | `30` | Active observed seconds required to count a play, limited to 1–3600. |
| `PAUSE_GRACE_SEC` | `30` | Seconds to retain a paused or missing session, limited to 0–3600. |
| `CHECKPOINT_INTERVAL_SEC` | `60` | Refresh interval for durable active-session checkpoints, limited to 10–3600 seconds. |
| `SAVE_RETRY_ATTEMPTS` | `3` | Database save attempts for a session, limited to 1–10. |
| `MAX_POLL_BACKOFF_SEC` | `60` | Maximum upstream failure backoff, limited to 1–3600 seconds. |
| `BACKFILL_INTERVAL_SEC` | `3600` | How often a configured smart-playlist backfill is re-checked, limited to 300–86400 seconds. |
| `BACKFILL_CUTOFF_MARGIN_SEC` | `60` | Safety margin subtracted from live-poller coverage before importing, limited to 0–3600 seconds. |
| `RETENTION_MAINTENANCE_SEC` | `86400` | Automatic retention cleanup interval, limited to 60–604800 seconds. |
| `SESSION_COOKIE_SECURE` | `false` | Marks the login cookie Secure; enable it when users access the service through HTTPS. |

Environment variables are parsed when the application starts. Restart the container after changing them.

## How plays are counted

A track counts once its accumulated active observation time reaches `PLAY_THRESHOLD_SEC`. Paused and missing intervals are excluded. Reaching the threshold creates a checkpoint; later checkpoints and session finalization update the same database row instead of adding another play.

When a server advertises the OpenSubsonic `playbackReport` extension, position and playback-state fields improve duration accounting. Other servers continue to work through regular polling. Sessions that end below the play threshold are stored separately as playback attempts.

The Recent Plays information control reports these below-threshold sessions as a share of observed playback attempts. Pre-install backfill and native-history imports are excluded from that rate because the application did not observe them as live sessions; records restored from a Navidrome Stat privacy archive retain their original accounting role.

## Recovering pre-install history

Optionally, a saved connection can watch a Navidrome smart playlist (an `.nsp` such as "Recently Played"). On each check the service reads that playlist through the public `getPlaylist` API and stores one estimated play per track from its last-played timestamp. Re-runs never duplicate rows, listens already covered by live polling are skipped, and only plays that actually happened before installation are imported — older repeats implied by a track's play count are never invented. Configure the playlist ID per connection on the settings page.

More detail is available in [Architecture](docs/architecture.md).

## Operations

### Logs

```bash
docker compose logs -f --tail=100 navidrome-stat
```

The published container disables request access logs so dashboard filters, usernames, and source identifiers in application URLs are not written to container logs. Application logs also avoid playback metadata and upstream request URLs. Custom application servers, reverse proxies, and Navidrome may have their own access logs, so review their logging configuration before sharing logs.

### Troubleshooting

| Symptom | What to check |
| --- | --- |
| `/health` is healthy but `/health/ready` is degraded or not ready | Inspect the database, collector, upstream, and persistence checks in `/health/ready`. Confirm that at least one complete connection is enabled, the data directory is writable, and the container can reach Navidrome. |
| A saved connection does not collect playback | Open **Settings > Connections** and follow the diagnosis for authentication, TLS, timeout, network, or collector failures. Confirm the connection is enabled, then inspect `docker compose logs` if the issue remains. |
| Login repeats or API requests return `401` | Enter the current `STATS_API_TOKEN`. Behind HTTPS, set `SESSION_COOKIE_SECURE=true`; leave it `false` when accessing the service over plain HTTP. |
| SQLite cannot be opened or written | Confirm that `DATABASE_URL` points inside the mounted data volume and that UID and GID `1000:1000` can write the directory and database files. |

### Update

```bash
docker compose pull
docker compose up -d
```

Back up the data volume and review the changelog before updating a pinned version.

### Backup and restore

The data volume contains listening history and the credential key file and may contain saved Navidrome credentials. Treat backups as sensitive.

Stop the service and archive the complete data volume so the database and its matching `secret.key` stay together:

```bash
mkdir -p backups
docker compose stop navidrome-stat
docker run --rm \
  --volumes-from navidrome-stat:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.20 \
  tar -C /data -czf /backup/navidrome-stat-data.tar.gz .
docker compose start navidrome-stat
```

Before relying on a backup, extract it outside the production volume and run SQLite's integrity check against the restored copy:

```bash
mkdir -p restore-test
docker run --rm \
  -v "$PWD/backups:/backup:ro" \
  -v "$PWD/restore-test:/restore" \
  alpine:3.20 \
  tar -C /restore -xzf /backup/navidrome-stat-data.tar.gz
test -f restore-test/navidrome_stats.db
test -f restore-test/secret.key || echo "No credential key in this archive"
docker compose run --rm --no-deps \
  -e DATABASE_URL=/restore/navidrome_stats.db \
  -v "$PWD/restore-test:/restore:ro" \
  navidrome-stat \
  python -c "import sqlite3; db = sqlite3.connect('file:/restore/navidrome_stats.db?mode=ro', uri=True); result = db.execute('PRAGMA integrity_check').fetchone()[0]; assert result == 'ok', result; print(result)"
```

To restore production, stop the service, preserve the current volume, extract the verified archive into an empty replacement volume, and ensure UID and GID `1000:1000` can write the restored files. Start the pinned application version, verify `/health/ready`, and test a saved connection. If the archive has no `secret.key`, re-enter saved passwords in Settings. Never merge an archive into a running or non-empty data volume.

## Security and privacy

- Without `STATS_API_TOKEN`, dashboard data and APIs are anonymous. Use this only on a trusted network.
- `STATS_API_TOKEN` grants one shared authorization level for viewing data, changing connections and settings, and running import, retention, or deletion operations. It is not a read-only user account.
- `/health` and `/health/ready` remain public. `/metrics` is public by default unless `STATS_METRICS_AUTH=true` is used with a token.
- `/metrics` includes polling and persistence health plus Dashboard build/cache, fixed-section query timing and budget violations, SQLite busy retry, import-duration, and cover-art cache metrics.
- Static dashboard files remain loadable when authentication is enabled; their data requests require authorization.
- The browser policy restricts scripts and styles to this service, blocks executable inline scripts, embedded objects, and cross-origin form targets, while permitting inline styles used by the bundled pages.
- Listening records are kept indefinitely by default. Saving a finite 1–360 day policy authorizes automatic cleanup at startup and during background maintenance.
- Inform affected users before collecting their listening activity and choose an appropriate retention period.

See [Privacy](docs/privacy.md) and the [security policy](SECURITY.md) for details.

## Development

Python 3.11 is the supported runtime.

New local checkouts keep the database, credential key, and cover-art cache under `.data/`, which is ignored by Git. If a legacy root-level `navidrome_stats.db` exists, it remains in use until you explicitly move the database and matching `secret.key` together or set `DATABASE_URL`.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest -q --cov=src --cov-report=term-missing --cov-fail-under=80
uvicorn src.main:app --host 127.0.0.1 --port 39421 --no-access-log
```

The repository also includes a development-oriented [`docker-compose.yml`](docker-compose.yml) that builds the current checkout:

```bash
git clone https://github.com/StepaniaH/navidrome-stat.git
cd navidrome-stat
docker compose up -d --build
```

Frontend assets and browser tests use Node.js:

```bash
npm ci
npm run test:unit
npx playwright install chromium
npm run test:e2e
```

Tests use temporary databases and synthetic API data; they do not require a live Navidrome server.

## Project information

- [Architecture](docs/architecture.md)
- [Compatibility policy](docs/compat.md)
- [Roadmap](docs/roadmap.md)
- [Privacy](docs/privacy.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)

## License

Navidrome Stat is available under the [MIT License](LICENSE). Bundled Tailwind CSS and Apache ECharts retain their respective license and notice files under `src/static/vendor/`.
