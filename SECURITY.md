# Security policy

## Supported versions

Security fixes target the default branch and the latest tagged release. Older releases are not maintained separately.

## Reporting a vulnerability

Please report vulnerabilities privately through [GitHub Security Advisories](https://github.com/StepaniaH/navidrome-stat/security/advisories/new).

Do not include vulnerability details, credentials, tokens, `.env` contents, database files, logs, or listening history in a public issue. If private reporting is unavailable, open a public issue requesting a private contact channel without describing the vulnerability.

Include the following in a private report when possible:

- The affected version or image tag
- The expected security impact
- Redacted reproduction steps or a minimal proof of concept
- Any suggested mitigation

## Deployment responsibilities

Navidrome Stat stores listening history and server configuration in SQLite. Protect the application, its Docker volume, exported data, and backups as sensitive resources.

The application does not terminate TLS. Use a trusted network or a TLS-enabled reverse proxy, and configure `STATS_API_TOKEN` before exposing the service outside a private network. Without either dashboard token, all dashboard and administrative APIs are available without authentication. `/health` and `/health/ready` are always public; `/metrics` is public unless `STATS_METRICS_AUTH=true`.

`STATS_API_TOKEN` grants administrator access. `STATS_READ_ONLY_TOKEN` grants access to statistics and Listening Review pages without allowing settings, connection, import, retention, deletion, OpenAPI, or protected metrics operations. Viewer access can be restricted with `STATS_READ_ONLY_SOURCE_ID` and `STATS_READ_ONLY_USERNAME`; these restrictions are enforced by the backend. Cover art for a username-scoped viewer is limited to sources containing history for that username.

The ListenBrainz receiver uses `LISTENBRAINZ_INGEST_TOKEN` and accepts it only in the `Authorization: Token` header. Administrator, viewer, and ingestion tokens must be different; the application refuses to start when configured credentials share a value. Use separate long, random values and avoid placing tokens in URLs or logs.

Review the deployment guidance in [`docs/deployment.md`](docs/deployment.md) and the data-handling details in [`docs/privacy.md`](docs/privacy.md).
