# Roadmap

Navidrome Statistic is a small, self-hosted service for aggregating playback activity across Subsonic-compatible clients, devices, users, and Navidrome servers.

This roadmap describes project direction, not release commitments. Shipped changes are recorded in the [changelog](../CHANGELOG.md), while concrete proposals and bugs belong in GitHub issues.

## Near term

- Keep contributor and maintainer workflows reproducible, including dependency-lock refresh, frontend asset builds, browser tests, the statistics benchmark, the container smoke test, and tag-only Docker releases.
- Extend the redacted connection diagnosis only when a new operator action can be recommended without exposing credentials, source identity, or playback metadata.

## Medium term

- Improve large-history query, cache, and retention performance within the existing single-host SQLite architecture, using the multi-scale synthetic baseline and query-plan checks to evaluate changes.
- Watch upstream for a public Navidrome listening-history read API (the `getSongHistory` proposal) so the existing guarded importer can be enabled against a released endpoint.
- Offer opt-in ListenBrainz-format scrobble forwarding with per-server deduplication.

## Long term

- Optional read-only sharing links for filtered dashboard views.
- Library-quality panels (format, bitrate, and decade distribution) from `search3` metadata.
- Pluggable enrichment adapters (cover art today; artist images and similar-track hints when upstream agents are configured).

## Non-goals

- Playing music, managing queues or libraries, or replacing a Navidrome client.
- Reading or writing Navidrome's private database; upstream integration remains through Subsonic and OpenSubsonic APIs.
- Multi-worker collectors, active-active replicas, distributed coordination, or shared-network SQLite.
- Built-in TLS termination or reverse-proxy functionality.
