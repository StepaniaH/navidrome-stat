# Changelog

All notable user-facing changes are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Dashboard filters, custom date ranges, localized settings, and independent loading, empty, and error states.
- Optional authentication for `/metrics` through `STATS_METRICS_AUTH`.
- Optional OpenAPI route disabling through `OPENAPI_ENABLED`.
- Public project metadata through `/api/about`.

### Changed

- Release automation now runs only for `v*` tags and publishes the corresponding Docker image to Docker Hub.
- Documentation was consolidated around deployment, architecture, privacy, contributing, and security guidance.
- The bundled Tailwind stylesheet was rebuilt from the current dashboard and settings templates.
- Import requests without a `Content-Length` header are limited while streaming and stop being consumed as soon as they exceed 5 MiB.

### Fixed

- Authentication handles non-ASCII token input as an authorization failure instead of a server error.
- Unauthorized API responses retain security headers, and unauthorized imports are rejected before their request body is read.
- Collector teardown always closes clients and removes runtime state, including when a polling task has already failed.
- Persistence failures remain isolated from successful upstream polls, while tracker failures trigger the normal poll backoff.
- Empty replacement imports invalidate cached statistics, and malformed playback attempts return a validation error.
- Retention cleanup, daylight-saving-time date ranges, task health metrics, and client-name rendering are handled more reliably.
- The frontend build lockfile uses the patched `nanoid` release required by the current security advisory.
- A successful upstream response with no `nowPlaying` payload is treated as idle playback.

## [0.7.0] - 2026-07-28

### Added

- Idempotent play checkpoints, OpenSubsonic playback-report support, and duration-confidence tracking.
- Multi-server identity, per-source health, and dashboard snapshot caching.
- Privacy export format version 2, bounded imports, and upstream log redaction.
- Self-hosted Tailwind CSS and ECharts assets.

### Changed

- Content Security Policy no longer permits public CDN origins.

## [0.6.0] - 2026-07-27

### Added

- Server changes hot-reload collectors without restarting the process.

## [0.5.4] - 2026-07-27

### Added

- Complete frontend localization for dashboard and settings text.

## [0.5.3] - 2026-07-27

The published tag points to the same source revision as `v0.5.0` and contains no additional changes. Use `v0.5.4` or later when pinning an image.

## [0.5.2] - 2026-07-26

### Fixed

- Ranking rows no longer overflow the page layout.

## [0.5.1] - 2026-07-26

### Added

- Multi-server dashboard settings.
- Tagged Docker images published through CI.

## [0.5.0] - 2026-07-16

### Added

- Initial tagged release of the polling statistics service with optional `STATS_API_TOKEN` authentication.

[Unreleased]: https://github.com/StepaniaH/navidrome-stat/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.7.0
[0.6.0]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.6.0
[0.5.4]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.5.4
[0.5.3]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.5.3
[0.5.2]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.5.2
[0.5.1]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.5.1
[0.5.0]: https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.5.0
