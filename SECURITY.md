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

The application does not terminate TLS. Use a trusted network or a TLS-enabled reverse proxy, and configure `STATS_API_TOKEN` before exposing the dashboard outside a private network. Review the deployment guidance in [`README.md`](README.md) and the data-handling details in [`docs/privacy.md`](docs/privacy.md).
