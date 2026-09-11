# Docker deployment

[简体中文](deployment.zh-CN.md) · [Documentation](README.md)

## Requirements

- Docker Engine with Docker Compose v2
- Network access from the container to each Navidrome server
- A Navidrome account that can call the Subsonic API

## 1. Create a deployment directory

```bash
mkdir navidrome-stat
cd navidrome-stat
```

## 2. Create `.env`

Use a long, random value for `STATS_API_TOKEN`. Do not commit this file or include it in support logs.

```dotenv
NAVIDROME_URL=https://navidrome.example.invalid
NAVIDROME_USER=example_user
NAVIDROME_PASS=<navidrome-password>
STATS_API_TOKEN=<long-random-token>
# Optional read-only dashboard credential and fixed scope:
# STATS_READ_ONLY_TOKEN=<different-long-random-token>
# STATS_READ_ONLY_SOURCE_ID=server-id
# STATS_READ_ONLY_USERNAME=example_user

POLL_INTERVAL=10
PLAY_THRESHOLD_SEC=30
MAX_INFERRED_INTERVAL_SEC=30
PAUSE_GRACE_SEC=30
```

The three `NAVIDROME_*` variables provide one fallback connection when no server entries have been saved. For this fallback, each non-empty environment value takes precedence over the corresponding value already stored in SQLite. Once any entry exists under **Settings > Connections**, only enabled entries from that list are collected; the fallback is not used, even when every saved entry is disabled.

To aggregate multiple servers, add each connection from **Settings > Connections** after startup. Credentials saved there are encrypted at rest with a per-installation key file (`secret.key`) generated beside the SQLite database. Back up that file together with the database, or plan to re-enter passwords after restoring a database-only copy; the encryption protects database copies and backups from casual inspection, not a fully compromised host. If that storage model is unsuitable, use only the single environment-configured connection and do not save connections through the settings page.

## 3. Create `compose.yaml`

The example pins the current stable release, `v0.9.3`. The `latest` tag follows stable releases.

```yaml
services:
  navidrome-stat:
    image: stepaniah/navidrome-statistic:v0.9.3
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
      STATS_READ_ONLY_TOKEN: ${STATS_READ_ONLY_TOKEN:-}
      STATS_READ_ONLY_SOURCE_ID: ${STATS_READ_ONLY_SOURCE_ID:-}
      STATS_READ_ONLY_USERNAME: ${STATS_READ_ONLY_USERNAME:-}
      LISTENBRAINZ_INGEST_TOKEN: ${LISTENBRAINZ_INGEST_TOKEN:-}
      LISTENBRAINZ_INGEST_USERNAME: ${LISTENBRAINZ_INGEST_USERNAME:-}
      DATABASE_URL: /data/navidrome_stats.db
      POLL_INTERVAL: ${POLL_INTERVAL:-10}
      PLAY_THRESHOLD_SEC: ${PLAY_THRESHOLD_SEC:-30}
      MAX_INFERRED_INTERVAL_SEC: ${MAX_INFERRED_INTERVAL_SEC:-30}
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

## 4. Start the service

```bash
docker compose up -d
docker compose ps
```

Open `http://localhost:39421`. When an administrator or viewer token is configured, enter it in the login screen; the browser stores an HttpOnly role-specific session cookie rather than the token itself.

`/health` reports process liveness. `/health/ready` also checks the database, collectors, upstream polling, and durable playback writes. An upstream or database failure can therefore make readiness degraded or not ready while the process remains healthy.

## Runtime requirements

- Run a single Navidrome Stat instance for a set of sources. Multiple instances polling the same sources can double-count plays.
- Active sessions are held in one process. Multi-worker Uvicorn deployments are not supported.
- Listening records in SQLite are stored unencrypted; saved server credentials are encrypted at rest with a local key file (`secret.key`) that is not a defense against a fully compromised host.
- The application does not provide TLS. Use a trusted network or an HTTPS reverse proxy for remote access.
- Keep SQLite on local storage; shared network filesystems are not supported.

See the [configuration reference](configuration.md) for every variable. Additional variables in `.env` must also be passed through `environment` in `compose.yaml`. See [operations](operations.md) for updates, backups, and troubleshooting.
