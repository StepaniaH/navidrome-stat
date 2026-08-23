# Privacy

Navidrome Statistic stores listening activity so it can build a shared dashboard across Navidrome servers, clients, and devices. This page describes what the application handles and what operators should protect.

## Data stored

The SQLite database can contain:

- Navidrome usernames;
- track IDs, titles, artists, and albums;
- client names and transcoding status;
- playback timestamps and observed listening duration;
- Navidrome server identifiers and display names;
- counted plays and below-threshold playback attempts;
- retention settings and internal session checkpoints.

These fields can reveal personal listening habits when combined, even when the media metadata is otherwise public.

## Navidrome credentials

Credentials supplied through `NAVIDROME_URL`, `NAVIDROME_USER`, and `NAVIDROME_PASS` remain in the process environment and memory. Credentials saved from **Settings > Connections** are stored in plaintext in SQLite so the service can reconnect after a restart.

The settings APIs return configured URLs and usernames to authorized viewers, but never return saved passwords. Protect the database, Docker volume, `.env` file, and backups as credentials.

Subsonic authentication uses token and salt query parameters. The application avoids logging upstream request URLs, but reverse proxies, network tools, and the Navidrome server may have their own access logs. Configure those systems so authentication query parameters are not retained or shared.

## Retention and data controls

Listening records are retained permanently by default. The settings page can change retention to 1–360 days and provides preview and confirmation steps before deletion.

Per-user controls support JSON export, import, and deletion. Exports contain listening activity and should be handled as sensitive files. Deleting data from the application database does not remove copies already present in backups or external storage.

SQLite uses write-ahead logging. The database file, `-wal` and `-shm` files, volume snapshots, and backups can all contain the same sensitive data. Stop the application before taking a simple file-level backup, as shown in the README.

## Browser and network behavior

Language, theme, timezone, and reduced-motion preferences are stored in browser `localStorage`. They do not include listening history or Navidrome credentials. The selected timezone is sent with statistics requests to calculate local date and hour buckets.

Frontend assets are served by the application. Normal dashboard use does not load JavaScript or CSS from a public CDN, and the project does not include usage analytics or telemetry.

Without `STATS_API_TOKEN`, dashboard data and APIs are available to anyone who can reach the service. The application does not provide TLS; use a trusted network or an HTTPS reverse proxy with appropriate access control.

## Operator checklist

- Tell affected users what listening activity is collected and why.
- Set `STATS_API_TOKEN` or equivalent proxy authentication when access is not limited to a trusted network.
- Restrict access to `.env`, SQLite files, Docker volumes, exports, and backups.
- Review proxy and Navidrome logs for authentication query parameters.
- Choose a retention period and backup policy appropriate for the deployment.
- Use synthetic or redacted data in issues, logs, screenshots, and test fixtures.
