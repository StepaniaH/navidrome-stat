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

Cover art requested through the application is cached on disk inside the container or host volume, in a size-capped directory. The cache holds only artwork fetched for the dashboard and can be cleared by removing that directory; it is not part of the SQLite database or its backups.

These fields can reveal personal listening habits when combined, even when the media metadata is otherwise public.

## Navidrome credentials

Credentials supplied through `NAVIDROME_URL`, `NAVIDROME_USER`, and `NAVIDROME_PASS` remain in the process environment and memory. Credentials saved from **Settings > Connections** or through the compatible fallback `/api/source/config` endpoint are encrypted at rest with AES-256-GCM. The per-installation key file, `secret.key`, is stored beside the SQLite database and must be backed up with it; restoring the database without that key leaves saved passwords unavailable until they are entered again.

The settings APIs return configured URLs and usernames to authorized viewers, but never return saved passwords. Connection tests and `/api/diagnostics` return stable failure categories rather than upstream exception text. The diagnostics response contains aggregate connection, collector, and history counts but omits URLs, usernames, passwords, source IDs, and playback metadata; it is protected whenever `STATS_API_TOKEN` is configured. Protect the database, Docker volume, `.env` file, and backups as credentials.

Subsonic authentication uses token and salt query parameters. The application avoids logging upstream request URLs, but reverse proxies, network tools, and the Navidrome server may have their own access logs. Configure those systems so authentication query parameters are not retained or shared.

## Retention and data controls

Listening records are retained permanently by default. Saving a finite retention policy of 1–360 days authorizes the service to delete older records during startup and periodic background maintenance. The settings page previews the affected records and asks for confirmation before saving a finite policy. Its separate **Apply now** action has its own preview and confirmation before running the purge immediately. That action is bound to the policy used for its preview; if another session changes the saved policy, no records are deleted until the preview is refreshed.

Per-user controls support JSON export, import, and deletion. Exports contain listening activity and should be handled as sensitive files. Deleting data from the application database does not remove copies already present in backups or external storage.

SQLite uses write-ahead logging. The database file, `-wal` and `-shm` files, volume snapshots, and backups can all contain the same sensitive data. Stop the application before taking a simple file-level backup, as shown in the README.

## Browser and network behavior

Language, theme, timezone, and reduced-motion preferences are stored in browser `localStorage`. The theme runtime recognizes four keys: `navidrome-theme-mode` and `navidrome-theme-palette` hold the current choices, `navidrome-theme` is read and maintained as a compatibility value for earlier releases, and `navidrome-theme-customizations` contains versioned color overrides keyed by built-in theme ID. These values contain only appearance identifiers and hexadecimal colors, not listening history or Navidrome credentials. Theme JSON import is read locally by the browser and is not uploaded; export creates a local download containing the selected preset ID and six colors. System theme mode reads the browser's `prefers-color-scheme` media query and cannot read or change operating-system settings. Theme preferences are not sent to the server. The selected timezone is sent with statistics requests to calculate local date and hour buckets.

Frontend assets are served by the application. Normal dashboard use does not load JavaScript or CSS from a public CDN, and the project does not include usage analytics or telemetry. The published container disables Uvicorn request access logs because application URLs can contain usernames, source identifiers, and dashboard filters. Operators using another application server or reverse proxy should apply an equivalent logging policy.

Without `STATS_API_TOKEN`, dashboard data and APIs are available to anyone who can reach the service. The application does not provide TLS; use a trusted network or an HTTPS reverse proxy with appropriate access control.

## Operator checklist

- Tell affected users what listening activity is collected and why.
- Set `STATS_API_TOKEN` or equivalent proxy authentication when access is not limited to a trusted network.
- Restrict access to `.env`, SQLite files, Docker volumes, exports, and backups.
- Review proxy and Navidrome logs for authentication query parameters.
- Choose a retention period and backup policy appropriate for the deployment.
- Use synthetic or redacted data in issues, logs, screenshots, and test fixtures.
