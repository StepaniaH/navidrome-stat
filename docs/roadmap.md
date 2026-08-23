# Roadmap

Navidrome Statistic is a small, self-hosted service for aggregating playback activity across Subsonic-compatible clients, devices, users, and Navidrome servers.

This roadmap describes project direction, not release commitments. Shipped changes are recorded in the [changelog](../CHANGELOG.md), while concrete proposals and bugs belong in GitHub issues.

## Near term

- Add migration fixtures and repeatable restore checks for existing SQLite deployments.
- Define a compatibility and deprecation path for the fallback single-source API alongside multi-server connections.
- Bound concurrent dashboard builds and make single-flight cache cleanup independent of request cancellation.
- Keep contributor and maintainer workflows reproducible, including dependency-lock refresh, frontend asset builds, browser tests, the statistics benchmark, the container smoke test, and tag-only Docker releases.
- Improve collector diagnostics while keeping health responses free of credentials and playback metadata.

## Medium term

- Define pre-1.0 compatibility rules for HTTP endpoints, privacy export formats, and SQLite migrations.
- Improve large-history query, cache, and retention performance within the existing single-host SQLite architecture, guided by synthetic benchmarks.
- Reduce credential exposure for saved multi-server connections without obscuring deployment, migration, or backup behavior.
- Incrementally separate application lifecycle and routes, schema and statistics queries, and dashboard runtime code while preserving user-facing behavior.

## Non-goals

- Playing music, managing queues or libraries, or replacing a Navidrome client.
- Reading or writing Navidrome's private database; upstream integration remains through Subsonic and OpenSubsonic APIs.
- Multi-worker collectors, active-active replicas, distributed coordination, or shared-network SQLite.
- Built-in TLS termination or reverse-proxy functionality.
