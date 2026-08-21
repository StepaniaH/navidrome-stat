# Navidrome Statistic

[简体中文](README.zh-CN.md)

Navidrome Statistic is a self-hosted service that polls the Subsonic `getNowPlaying` API, tracks listening sessions, stores qualified plays in SQLite, and presents the results in a web dashboard.

It is designed for a single application instance. Multiple Navidrome servers can be configured, but running multiple Navidrome Statistic replicas against the same sources is not supported and may double-count plays.

## Features

- Tracks active playback with a configurable threshold, pause grace period, idempotent checkpoints, and final session duration.
- Uses OpenSubsonic playback reports when advertised and records whether duration is reported or estimated; older servers continue to work through polling.
- Supports multiple Navidrome servers with per-server filtering and collector health.
- Shows current playback, listening history, clients, transcoding, time trends, and artist or album rankings.
- Records below-threshold attempts separately from counted plays.
- Provides configurable retention and per-user JSON export, import, and deletion.
- Groups connections, privacy, local preferences, and project information in an accessible settings page; language, theme, timezone, and reduced-motion preferences stay in the browser.
- Offers optional dashboard and API authentication through `STATS_API_TOKEN`.
- Provides a responsive filter bar with preset or custom inclusive date ranges and per-server filtering.
- Serves pinned frontend assets locally; normal dashboard use does not contact a public CDN.
- Runs as a non-root user in a multi-stage Python 3.11 container.

## Docker Deployment

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

These three `NAVIDROME_*` variables configure the initial or legacy source. Additional servers can be added from **Settings > Connections** after startup. Values saved through the settings page are stored in plaintext in the application database; prefer environment variables when that storage model is unsuitable.

### 3. Create `compose.yaml`

Pin a version tag instead of `latest` when deployment reproducibility is more important than automatic access to the newest release.

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
      POLL_INTERVAL: ${POLL_INTERVAL:-10}
      PLAY_THRESHOLD_SEC: ${PLAY_THRESHOLD_SEC:-30}
      PAUSE_GRACE_SEC: ${PAUSE_GRACE_SEC:-30}
      CHECKPOINT_INTERVAL_SEC: ${CHECKPOINT_INTERVAL_SEC:-60}
      SAVE_RETRY_ATTEMPTS: ${SAVE_RETRY_ATTEMPTS:-3}
      MAX_POLL_BACKOFF_SEC: ${MAX_POLL_BACKOFF_SEC:-60}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-false}
      STATS_METRICS_AUTH: ${STATS_METRICS_AUTH:-false}
      OPENAPI_ENABLED: ${OPENAPI_ENABLED:-true}
      DATABASE_URL: /data/navidrome_stats.db
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

Open `http://localhost:39421`. When `STATS_API_TOKEN` is set, the dashboard asks for that token and stores only an HTTP-only session cookie in the browser.

The `/health` endpoint reports process liveness. `/health/ready` also reports database and collector state; a temporary upstream failure can make readiness degraded without requiring a container restart.

## Operations

### View logs

```bash
docker compose logs -f --tail=100 navidrome-stat
```

Application logs intentionally omit playback metadata and authentication request URLs. Avoid enabling or sharing infrastructure logs that contain Subsonic authentication query parameters.

### Update

```bash
docker compose pull
docker compose up -d
docker image prune
```

Back up the database before an update. Review release notes before changing a pinned image tag.

### Back up and restore

The named volume contains the SQLite database, listening history, and any server credentials saved through the settings page. Treat every backup as sensitive.

Stop the application before copying the database:

```bash
mkdir -p backups
docker compose stop navidrome-stat
docker run --rm \
  -v navidrome-stat_navidrome-stat-data:/data:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.20 \
  cp /data/navidrome_stats.db /backup/navidrome_stats.db
docker compose start navidrome-stat
```

The actual volume name is shown by `docker volume ls`; Compose usually prefixes it with the deployment directory name. Store backups in an access-controlled location and define an appropriate retention policy.

To restore, stop the service, preserve the current volume, copy a verified backup to `/data/navidrome_stats.db`, ensure UID and GID `1000:1000` can write it, and then start the service. Test restoration away from the production volume first.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `NAVIDROME_URL` | None | Initial Navidrome base URL. Required unless a complete source was previously saved. |
| `NAVIDROME_USER` | None | Initial Subsonic username. |
| `NAVIDROME_PASS` | None | Initial Subsonic password. |
| `DATABASE_URL` | `navidrome_stats.db` | SQLite file path. The Docker example uses `/data/navidrome_stats.db`. |
| `STATS_API_TOKEN` | Empty | Protects the dashboard, statistics APIs, settings APIs, and OpenAPI routes when set. |
| `STATS_METRICS_AUTH` | `false` | When `true` and `STATS_API_TOKEN` is set, `/metrics` requires the same authentication as the statistics APIs. |
| `OPENAPI_ENABLED` | `true` | Set to `false` to unregister `/docs`, `/redoc`, and `/openapi.json`. |
| `POLL_INTERVAL` | `10` | Poll interval in seconds, clamped to 5-300. |
| `PLAY_THRESHOLD_SEC` | `30` | Active observed seconds required to count a play, clamped to 1-3600. |
| `PAUSE_GRACE_SEC` | `30` | Seconds to retain a paused or missing in-memory session, clamped to 0-3600. |
| `CHECKPOINT_INTERVAL_SEC` | `60` | Refresh interval for durable active-session checkpoints, clamped to 10-3600 seconds. |
| `MAX_POLL_BACKOFF_SEC` | `60` | Maximum upstream failure backoff, clamped to 1-3600 seconds. |
| `SAVE_RETRY_ATTEMPTS` | `3` | Database save attempts for a session, clamped to 1-10. A failed save remains retryable. |
| `SESSION_COOKIE_SECURE` | `false` | Set to `true` when the application is reached through HTTPS so the login cookie is marked Secure. |
| `RETENTION_MAINTENANCE_SEC` | `86400` | Retention cleanup interval, clamped to 60-604800 seconds. |

A track counts once its accumulated active time is greater than or equal to `PLAY_THRESHOLD_SEC`. That threshold creates an idempotent checkpoint, which is refreshed every `CHECKPOINT_INTERVAL_SEC`; session end updates the same row with the final active duration rather than adding another play. On startup, an interrupted checkpoint is finalized at its last persisted duration without inventing unobserved listening time. When the server advertises OpenSubsonic playback reports, media position and playback state improve the estimate. Otherwise those extension fields are ignored and the service uses poll intervals. Paused intervals are excluded.

## Security and Privacy

- Without `STATS_API_TOKEN`, the dashboard and APIs are anonymous. Use that mode only on a trusted network.
- The application does not terminate TLS. Place it behind a correctly configured HTTPS reverse proxy before remote access.
- SQLite stores usernames, media metadata, listening timestamps, and settings-page credentials in plaintext.
- Inform affected Navidrome users before collecting their listening activity and choose an appropriate retention period under **Settings > Privacy & Data**. A fill-in template is in [`docs/privacy-notice.template.md`](docs/privacy-notice.template.md); it is not legal advice.
- Protect `.env`, the Docker volume, backups, browser access, and reverse-proxy logs.
- Tailwind CSS and ECharts are pinned and served by the application itself. The browser CSP permits only same-origin scripts and styles.
- User exports use a fixed filename, include counted plays and short attempts, and can be imported from format version 1 or 2. Imports are bounded to 5 MiB and 10,000 records and validate timestamps, lengths, and duration ranges.

No generic Compose example can establish your authorization rules, TLS termination, backup security, or public exposure policy. Those remain deployment-owner decisions.

## Build from Source

The repository includes a development-oriented [`docker-compose.yml`](docker-compose.yml) that builds the local checkout:

```bash
git clone https://github.com/StepaniaH/navidrome-stat.git
cd navidrome-stat
docker compose up -d --build
```

Create `.env` from the placeholder example in the Docker deployment section before running Compose. Never place real credentials in a tracked file.

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

Runtime dependencies are pinned in `requirements.txt`; the fully resolved lock used by Docker is `requirements.lock`; test dependencies are in `requirements-dev.txt`.

To rebuild the pinned frontend assets and run synthetic browser tests:

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

The browser tests use a temporary SQLite database and intercepted synthetic API data. They do not require a real Navidrome account.

Run the reproducible time-bucket benchmark with synthetic data:

```bash
python -m scripts.benchmark_stats --rows 100000
```

## Documentation

- [Project documentation map](docs/README.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)
- [Open-source roadmap](docs/roadmap.md)
- [Current implementation](docs/current-state.md)
- [Interfaces and configuration](docs/interfaces.md)
- [Privacy boundaries](docs/privacy.md)
- [Security model](docs/security.md)
- [Task register](docs/tasks.md)

## License

Navidrome Statistic is available under the [MIT License](LICENSE).
Bundled Tailwind CSS and Apache ECharts retain their respective license and notice files under `src/static/vendor/`.
