# Changelog

All notable user-facing changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version tags are `vX.Y.Z`.

This file is reconstructed from public git tags and merge commits. It does not copy deployment addresses, credentials, or listening data.

## [Unreleased]

- Dashboard filter bar, custom date range, settings information architecture, and localization runtime (merged to `main` after `v0.7.0` via PR #7).
- Documentation map, contributor/security entry points, and the open-source roadmap.
- `/api/about` now returns the public GitHub repository URL.
- Tagged image publishes also create a GitHub Release.
- Optional `STATS_METRICS_AUTH` protects `/metrics` when `STATS_API_TOKEN` is set. Optional `OPENAPI_ENABLED=false` unregisters OpenAPI routes. Defaults keep previous anonymous metrics and enabled docs.
- Repository Compose file passes `SESSION_COOKIE_SECURE`, retry/backoff, metrics, and OpenAPI flags into the container.
- Auth compares tokens as UTF-8 bytes so non-ASCII input returns 401 instead of 500. Logout clears the session cookie with the same Secure/HttpOnly flags as login. An upstream `getNowPlaying` ok response with null `nowPlaying` is treated as idle, not a poll failure.

## [0.7.0] - 2026-07-28

- Idempotent play checkpoints, OpenSubsonic playback-report support, and duration confidence.
- Multi-server identity, per-source health, and dashboard snapshot caching.
- Privacy export format version 2, bounded import, and log redaction.
- Self-hosted Tailwind CSS and ECharts; CSP no longer allows public CDNs.

## [0.6.0] - 2026-07-27

- Server create/update/delete hot-reloads collectors without a process restart.

## [0.5.4] - 2026-07-27

- Complete frontend localization for dashboard and settings copy.

## [0.5.2] - 2026-07-26

- Prevent ranking rows from overflowing the layout.

## [0.5.1] - 2026-07-26

- Multi-server dashboard settings expansion.
- CI publishes tagged images to Docker Hub.

## [0.5.0] - 2026-07-16

- First tagged release of the polling statistic service with optional `STATS_API_TOKEN`.

`v0.5.3` points at the same commit as `v0.5.0`. Prefer `v0.5.4` and later when pinning images.

[Unreleased]: https://github.com/StepaniaH/navidrome-stat/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.7.0
[0.6.0]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.6.0
[0.5.4]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.5.4
[0.5.2]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.5.2
[0.5.1]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.5.1
[0.5.0]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.5.0
