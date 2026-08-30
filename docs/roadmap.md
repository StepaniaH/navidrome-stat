# Roadmap

Navidrome Stat is a small, self-hosted service for aggregating playback activity across Subsonic-compatible clients, devices, users, and Navidrome servers.

This roadmap describes project direction, not release commitments. Shipped changes are recorded in the [changelog](../CHANGELOG.md), while concrete proposals and bugs belong in GitHub issues.

## Near term

- Keep contributor and maintainer workflows reproducible, including dependency-lock refresh, frontend asset builds, browser tests, the statistics benchmark, the container smoke test, and verified tag-only container and GitHub releases.
- Add release SBOMs, image signing, and build provenance after the guarded release workflow has been exercised in production.
- Extend the redacted connection diagnosis only when a new operator action can be recommended without exposing credentials, source identity, or playback metadata.

## Medium term

- Add daily or hourly rollups only when fixed-section production query metrics and the multi-scale benchmark repeatedly exceed their budgets; keep raw SQLite history as the source of truth.
- Separate viewer and administrator authorization while preserving the shipped dashboard and year-in-review user scope.
- Watch upstream for a public Navidrome listening-history read API (the `getSongHistory` proposal) so the existing guarded importer can be enabled against a released endpoint.
- Offer opt-in ListenBrainz-format scrobble forwarding with per-server deduplication.

## Long term

- Time-limited read-only sharing links for explicitly scoped dashboard views.
- Library-quality panels (format, bitrate, and decade distribution) from `search3` metadata.
- Pluggable enrichment adapters (cover art today; artist images and similar-track hints when upstream agents are configured).

## Non-goals

- Playing music, managing queues or libraries, or replacing a Navidrome client.
- Reading or writing Navidrome's private database; upstream integration remains through Subsonic and OpenSubsonic APIs.
- Multi-worker collectors, active-active replicas, distributed coordination, or shared-network SQLite.
- Built-in TLS termination or reverse-proxy functionality.
