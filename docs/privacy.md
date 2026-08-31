# Privacy

Navidrome Stat stores listening activity so it can build a shared dashboard across Navidrome servers, clients, and devices. This page describes what the application handles and what operators should protect.

## Data stored

The SQLite database can contain:

- Navidrome usernames;
- track, artist, and album IDs, together with titles, artist names, and album names;
- client names and transcoding status;
- playback timestamps and observed listening duration;
- Navidrome server identifiers and display names;
- counted plays and below-threshold playback attempts;
- retention settings, internal session checkpoints, and stable record identifiers used to make imports idempotent.

Cover art requested through the application is cached on disk inside the container or host volume, in a size-capped directory. The cache holds only artwork fetched for the dashboard and can be cleared by removing that directory; it is not part of the SQLite database or its backups.

These fields can reveal personal listening habits when combined, even when the media metadata is otherwise public.

## Navidrome credentials

Credentials supplied through `NAVIDROME_URL`, `NAVIDROME_USER`, and `NAVIDROME_PASS` remain in the process environment and memory. Credentials saved from **Settings > Connections** or through the compatible fallback `/api/source/config` endpoint are encrypted at rest with AES-256-GCM. The per-installation key file, `secret.key`, is stored beside the SQLite database and must be backed up with it; restoring the database without that key leaves saved passwords unavailable until they are entered again.

The settings APIs return configured URLs and usernames to authorized sessions, but never return saved passwords. Connection tests and `/api/diagnostics` return stable failure categories rather than upstream exception text. The diagnostics response contains aggregate connection, collector, and history counts but omits URLs, usernames, passwords, source IDs, and playback metadata; it is protected whenever `STATS_API_TOKEN` is configured. Protect the database, Docker volume, `.env` file, and backups as credentials.

Subsonic authentication uses token and salt query parameters. The application avoids logging upstream request URLs, but reverse proxies, network tools, and the Navidrome server may have their own access logs. Configure those systems so authentication query parameters are not retained or shared.

## Retention and data controls

Listening records are retained permanently by default. Saving a finite retention policy of 1–360 days authorizes the service to delete older records during startup and periodic background maintenance. The settings page previews the affected records and asks for confirmation before saving a finite policy. Its separate **Apply now** action has its own preview and confirmation before running the purge immediately. That action is bound to the policy used for its preview; if another session changes the saved policy, no records are deleted until the preview is refreshed.

Retention cleanup deletes rows but does not run SQLite `VACUUM`. Deleted pages remain inside the database file for SQLite to reuse, so the preview reports affected records and estimated deleted record payload without claiming that the file or operating-system disk usage will shrink.

Per-user controls support JSON export, import, and deletion. Format v3 exports include each row's stable record ID and a SHA-256 fingerprint of its normalized contents. These values let repeated imports distinguish duplicates from conflicting rows; they are not credentials, but they remain part of the sensitive listening-history export and can link copies of the same exported record. Formats v1 and v2 remain importable and receive deterministic identities during import.

Deleting a user discards that user's active in-memory sessions and suppresses writes already queued for those sessions. Playback observed after deletion starts a new session and is collected normally. Deletion from the application database does not remove exports or copies already present in backups or external storage.

The database retains a history-import checkpoint and a deletion cutoff after deletion so history and playlist imports cannot restore older records. Their keys use SHA-256 digests of the source ID and username. The history checkpoint records the next offset, completion status, failure count, and next retry time; the deletion cutoff records the UTC deletion time. Neither value contains the cleartext username or listening metadata. Removing the application database also removes these markers.

SQLite uses write-ahead logging. The database file, `-wal` and `-shm` files, volume snapshots, and backups can all contain the same sensitive data. Stop the application before taking a simple file-level backup, as shown in the README.

## Browser and network behavior

Language, theme, timezone, and reduced-motion preferences are stored in browser `localStorage`. The theme runtime recognizes four keys: `navidrome-theme-mode` and `navidrome-theme-palette` hold the current choices, `navidrome-theme` is read and maintained as a compatibility value for earlier releases, and `navidrome-theme-customizations` contains versioned color overrides keyed by built-in theme ID. These values contain only appearance identifiers and hexadecimal colors, not listening history or Navidrome credentials. Theme JSON import is read locally by the browser and is not uploaded; export creates a local download containing the selected preset ID and six colors. System theme mode reads the browser's `prefers-color-scheme` media query and cannot read or change operating-system settings. Theme preferences are not sent to the server. The selected timezone is sent with statistics requests to calculate local date and hour buckets.

Frontend assets are served by the application. Normal dashboard use does not load JavaScript or CSS from a public CDN, and the project does not include usage analytics or telemetry. The published container disables Uvicorn request access logs because application URLs can contain usernames, source identifiers, and dashboard filters. Operators using another application server or reverse proxy should apply an equivalent logging policy.

Navidrome Stat has one shared authorization level. Anyone with `STATS_API_TOKEN` can view all stored listening data and configured connection identities, change settings and connections, and use export, import, retention, and deletion controls. There are no separate viewer and administrator roles. Do not distribute the token as a read-only credential; use an access-controlled reverse proxy if deployments need that separation.

Without `STATS_API_TOKEN`, dashboard data and all application APIs, including administrative and deletion operations, are available to anyone who can reach the service. The application does not provide TLS; use a trusted network or an HTTPS reverse proxy with appropriate access control.

## Operator checklist

- Tell affected users what listening activity is collected and why.
- Set `STATS_API_TOKEN` or equivalent proxy authentication when access is not limited to a trusted network.
- Give the shared token only to people who may change settings and delete data.
- Restrict access to `.env`, SQLite files, Docker volumes, exports, and backups.
- Review proxy and Navidrome logs for authentication query parameters.
- Choose a retention period and backup policy appropriate for the deployment.
- Use synthetic or redacted data in issues, logs, screenshots, and test fixtures.
