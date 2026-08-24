<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/icon-dark.svg">
  <img src="assets/icon.svg" alt="Navidrome Statistic" width="160">
</picture>

# Navidrome Statistic

</div>

[简体中文](README.zh-CN.md)

Navidrome Statistic collects playback activity reported by Navidrome and presents it in one dashboard. It provides a consistent view across Subsonic-compatible clients, browsers, phones, computers, and multiple Navidrome servers without requiring every client to implement its own statistics.

The service polls `getNowPlaying`, tracks listening sessions in memory, stores results in SQLite, and serves a self-contained web interface.

## Features

- Aggregates current and historical playback across clients, devices, users, and Navidrome servers.
- Shows listening time, play history, hourly and daily trends, client usage, transcoding, and artist or album rankings.
- Uses configurable play and pause thresholds, durable session checkpoints, and OpenSubsonic playback progress when available.
- Supports per-server filtering, connection management, retention settings, and per-user JSON export, import, and deletion.
- Offers optional token authentication for dashboard data and APIs.
- Serves pinned frontend assets locally and runs as a non-root user in the published container.

## Important limitations

- Run a single Navidrome Statistic instance for a set of sources. Multiple instances polling the same sources can double-count plays.
- Active sessions are held in one process. Multi-worker Uvicorn deployments are not supported.
- SQLite and any credentials saved through the settings page are stored in plaintext.
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

To aggregate multiple servers, add each connection from **Settings > Connections** after startup. Credentials saved there are stored in plaintext in SQLite. If that storage model is unsuitable, use only the single environment-configured connection and do not save connections through the settings page.

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

`/health` reports process liveness. `/health/ready` also checks the database and collectors, so a temporary upstream failure can make readiness degraded while the process remains healthy.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `NAVIDROME_URL` | None | Fallback Navidrome base URL; used only while the saved server list is empty. |
| `NAVIDROME_USER` | None | Username for the fallback Subsonic connection. |
| `NAVIDROME_PASS` | None | Password for the fallback Subsonic connection. |
| `DATABASE_URL` | `navidrome_stats.db` | SQLite file path; despite the name, this is not a general database URL. |
| `STATS_API_TOKEN` | Empty | Protects dashboard data, application APIs, and OpenAPI routes when set. |
| `STATS_METRICS_AUTH` | `false` | Requires authentication for `/metrics` when both this option and `STATS_API_TOKEN` are set. |
| `OPENAPI_ENABLED` | `true` | Set to `false` to remove `/docs`, `/redoc`, and `/openapi.json`. |
| `POLL_INTERVAL` | `10` | Poll interval in seconds, limited to 5–300. |
| `PLAY_THRESHOLD_SEC` | `30` | Active observed seconds required to count a play, limited to 1–3600. |
| `PAUSE_GRACE_SEC` | `30` | Seconds to retain a paused or missing session, limited to 0–3600. |
| `CHECKPOINT_INTERVAL_SEC` | `60` | Refresh interval for durable active-session checkpoints, limited to 10–3600 seconds. |
| `SAVE_RETRY_ATTEMPTS` | `3` | Database save attempts for a session, limited to 1–10. |
| `MAX_POLL_BACKOFF_SEC` | `60` | Maximum upstream failure backoff, limited to 1–3600 seconds. |
| `RETENTION_MAINTENANCE_SEC` | `86400` | Automatic retention cleanup interval, limited to 60–604800 seconds. |
| `SESSION_COOKIE_SECURE` | `false` | Marks the login cookie Secure; enable it when users access the service through HTTPS. |

Environment variables are parsed when the application starts. Restart the container after changing them.

## How plays are counted

A track counts once its accumulated active observation time reaches `PLAY_THRESHOLD_SEC`. Paused and missing intervals are excluded. Reaching the threshold creates a checkpoint; later checkpoints and session finalization update the same database row instead of adding another play.

When a server advertises the OpenSubsonic `playbackReport` extension, position and playback-state fields improve duration accounting. Other servers continue to work through regular polling. Sessions that end below the play threshold are stored separately as playback attempts.

More detail is available in [Architecture](docs/architecture.md).

## Operations

### Logs

```bash
docker compose logs -f --tail=100 navidrome-stat
```

Application logs avoid playback metadata and upstream request URLs. Reverse proxies and Navidrome may still log Subsonic authentication query parameters, so review their logging configuration before sharing logs.

### Troubleshooting

| Symptom | What to check |
| --- | --- |
| `/health` is healthy but `/health/ready` is degraded or not ready | Confirm that at least one complete connection is enabled, inspect the checks and collector counts in `/health/ready`, and check container-to-Navidrome network access. |
| A saved connection does not collect playback | Run its connection test in Settings, confirm it is enabled, and inspect `docker compose logs` for upstream failures. |
| Login repeats or API requests return `401` | Enter the current `STATS_API_TOKEN`. Behind HTTPS, set `SESSION_COOKIE_SECURE=true`; leave it `false` when accessing the service over plain HTTP. |
| SQLite cannot be opened or written | Confirm that `DATABASE_URL` points inside the mounted data volume and that UID and GID `1000:1000` can write the directory and database files. |

### Update

```bash
docker compose pull
docker compose up -d
```

Back up the database and review the changelog before updating a pinned version.

### Backup and restore

The data volume contains listening history and may contain saved Navidrome credentials. Treat backups as sensitive.

Stop the service before copying the SQLite file:

```bash
mkdir -p backups
docker compose stop navidrome-stat
docker run --rm \
  --volumes-from navidrome-stat:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.20 \
  cp /data/navidrome_stats.db /backup/navidrome_stats.db
docker compose start navidrome-stat
```

To restore, stop the service, preserve the current database, copy a verified backup to `/data/navidrome_stats.db`, ensure UID and GID `1000:1000` can write it, and start the service. Test restores away from the production volume first.

## Security and privacy

- Without `STATS_API_TOKEN`, dashboard data and APIs are anonymous. Use this only on a trusted network.
- `/health` and `/health/ready` remain public. `/metrics` is public by default unless `STATS_METRICS_AUTH=true` is used with a token.
- Static dashboard files remain loadable when authentication is enabled; their data requests require authorization.
- The browser policy restricts scripts and styles to this service, blocks executable inline scripts, embedded objects, and cross-origin form targets, while permitting inline styles used by the bundled pages.
- Listening records are kept indefinitely by default. Saving a finite 1–360 day policy authorizes automatic cleanup at startup and during background maintenance.
- Inform affected users before collecting their listening activity and choose an appropriate retention period.

See [Privacy](docs/privacy.md) and the [security policy](SECURITY.md) for details.

## Development

Python 3.11 is the supported runtime.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest -q --cov=src --cov-report=term-missing --cov-fail-under=80
uvicorn src.main:app --host 127.0.0.1 --port 39421
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

Navidrome Statistic is available under the [MIT License](LICENSE). Bundled Tailwind CSS and Apache ECharts retain their respective license and notice files under `src/static/vendor/`.
