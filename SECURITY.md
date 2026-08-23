# Security policy

This project is a self-hosted companion that stores listening history in a local SQLite file. Treat the database, Docker volume, backups, and any settings-page credentials as sensitive.

## Supported versions

Security fixes are accepted against the default branch and the latest tagged `vX.Y.Z` release. Older tags are not separately maintained.

## How to report

Do **not** open a public issue with credentials, tokens, `.env` contents, database files, or real play history.

1. Prefer a private [GitHub Security Advisory](https://github.com/StepaniaH/navidrome-stat/security/advisories/new) if that feature is enabled on the repository.
2. Otherwise contact the repository owner through GitHub without attaching secrets. Wait for a reply before sending details.

Whether private advisories are enabled is a repository-owner setting and is not claimed by this file.

## Known deployment boundaries

Documented in [`docs/security.md`](docs/security.md) and [`docs/privacy.md`](docs/privacy.md):

- Without `STATS_API_TOKEN`, the dashboard and statistics APIs are anonymous and must stay on a trusted network.
- `/health`, `/health/ready` remain reachable without a token. `/metrics` is public by default; set `STATS_METRICS_AUTH=true` when `STATS_API_TOKEN` is configured if the metrics endpoint should not be anonymous.
- Settings-page Navidrome passwords are stored in plaintext in SQLite when saved through the GUI. Prefer environment variables if that is unacceptable.
- The application does not terminate TLS.

Please include only redacted reproduction steps: status codes, exception types, and whether a field was present—not full request URLs.
