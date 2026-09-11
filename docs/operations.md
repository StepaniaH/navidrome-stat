# Operations

[简体中文](operations.zh-CN.md) · [Documentation](README.md)

## Logs

```bash
docker compose logs -f --tail=100 navidrome-stat
```

The published container disables request access logs so dashboard filters, usernames, source identifiers, and shareable artist or album detail names in application URLs are not written to container logs. Application logs also avoid playback metadata and upstream request URLs. Custom application servers, reverse proxies, and Navidrome may have their own access logs, so review their logging configuration before sharing logs.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `/health` is healthy but `/health/ready` is degraded or not ready | Inspect the database, collector, upstream, and persistence checks in `/health/ready`. Confirm that at least one complete connection is enabled, the data directory is writable, and the container can reach Navidrome. |
| A saved connection does not collect playback | Open **Settings > Connections** and follow the diagnosis for authentication, TLS, timeout, network, or collector failures. Confirm the connection is enabled, then inspect `docker compose logs` if the issue remains. |
| Login repeats or API requests return `401`/`403` | Enter the current administrator or viewer token. A `403` for settings or a different server/user is expected for viewers. Behind HTTPS, set `SESSION_COOKIE_SECURE=true`; leave it `false` over plain HTTP. |
| SQLite cannot be opened or written | Confirm that `DATABASE_URL` points inside the mounted data volume and that UID and GID `1000:1000` can write the directory and database files. |

## Update

For a pinned deployment, first change the image tag in `compose.yaml` to the desired release, then run the commands below. Leaving `v0.9.3` unchanged keeps that version; `latest` follows the newest stable release.

```bash
docker compose pull
docker compose up -d
```

Back up the data volume and review the changelog before updating a pinned version.

## Backup and restore

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

- Without either dashboard token, dashboard data and administrative APIs are anonymous. Use this only on a trusted network.
- `STATS_API_TOKEN` grants administrator access. `STATS_READ_ONLY_TOKEN` grants statistics, review, and related cover-art access; the backend rejects settings, connection, import, retention, deletion, OpenAPI, protected metrics, and out-of-scope requests.
- A fixed viewer source/username scope is enforced by the backend. Username-scoped viewers receive server options and cover art only for sources containing that user's history.
- Administrator, viewer, and ListenBrainz ingestion tokens must use different values.
- `/health` and `/health/ready` remain public. `/metrics` is public by default unless `STATS_METRICS_AUTH=true` is used with a token.
- `/metrics` includes polling and persistence health plus Dashboard build/cache, fixed-section query timing and budget violations, SQLite busy retry, import-duration, and cover-art cache metrics.
- Static dashboard files remain loadable when authentication is enabled; their data requests require authorization.
- The browser policy restricts scripts and styles to this service, blocks executable inline scripts, embedded objects, and cross-origin form targets, while permitting inline styles used by the bundled pages.
- Listening records are kept indefinitely by default. Saving a finite 1–360 day policy authorizes automatic cleanup at startup and during background maintenance.
- Inform affected users before collecting their listening activity and choose an appropriate retention period.

See [Privacy](privacy.md) and the [security policy](../SECURITY.md) for details.
