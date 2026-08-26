# Changelog

All notable user-facing changes are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.8.3] - 2026-08-26

### Added

- Filter the dashboard by user alongside the server filter; the selection is shareable through the URL and also narrows the now-playing list.
- Year-in-review distribution charts can switch between play counts and listening time.

### Fixed

- Chart update animations play in full instead of being cut short by the post-render resize pass.
- The year-in-review top lists render inside cards consistent with the chart panels.

## [0.8.2] - 2026-08-26

### Changed

- Interface translations live in one module per language with a shared registry; adding a language no longer requires touching page code.
- Dashboard ranking rows always reserve a cover slot: album tiles fall back to a letter block when artwork is unavailable, and rows keep their layout when covers load.
- Switching servers or date ranges now animates chart transitions instead of replacing them abruptly.
- The weekday-by-hour heatmap orders rows Monday-first, rounds cells with gutters, and derives its color ramp from the active color scheme.

### Fixed

- Selecting Deutsch on the settings page now applies immediately instead of silently falling back to English; the dashboard also gains the missing Traditional Chinese and Japanese catalogs.
- The heatmap color slider no longer overlaps the hour axis labels.

## [0.8.1] - 2026-08-25

### Added

- Configurable column visibility for the recent-plays table, persisted per browser with at least one column always enabled.
- The dashboard header shows the application version beside the brand, and the About panel lists it; both read `/api/about` instead of hardcoded strings.

### Changed

- The dashboard header shows the project brand name instead of a generic localized title.
- The year-in-review year picker uses the same popover style as the dashboard filters.
- The recent-plays server label appears under the username instead of beside the track title.

### Fixed

- Year-in-review charts render at full size on first load and no longer collide axis labels.
- Year-in-review top albums and tracks resolve cover art per source and fall back to letter tiles when unavailable.
- Server connection test results render in their own row instead of the connection form.
- The brand icon matches the reference artwork: circular note head, sound arcs clear of the outer ring, and a flush flag.

## [0.8.0] - 2026-08-24

### Added

- Cover art for play history, album rankings, and now-playing through an authenticated proxy with a size-capped disk cache; album names are resolved to Navidrome album IDs via `search3` with a 24-hour negative cache.
- A year-in-review page at `/review` with totals, streaks, monthly/hourly/weekday charts, and top artists, albums, and tracks.
- A `getSongHistory` capability probe per server, surfaced through the connections API ahead of an upstream read API.
- A pre-1.0 compatibility policy (docs/compat.md).
- German interface localization.
- Dashboard filters persist across reloads and are shareable through URL parameters.
- Dashboard charts recolor immediately when the theme preference changes in another tab.
- Dashboard filters, custom date ranges, localized settings, and independent loading, empty, and error states.
- Cross-server source labels, keyboard-complete filters, accessible login dialogs, and a first-run dashboard guide.
- Optional authentication for `/metrics` through `STATS_METRICS_AUTH`.
- Optional OpenAPI route disabling through `OPENAPI_ENABLED`.
- Project identity and version metadata through `/api/about`.
- A concise project roadmap plus reproducible benchmark, dependency-lock, browser-test, and release guidance.

### Changed
- The brand icon is now line art that adapts to the active theme; the favicon uses the same drawing.
- Ten themes ship out of the box: Catppuccin (Latte, Frappé, Macchiato, Mocha), Nord, Dracula, Tokyo Night, Gruvbox, and Solarized (dark and light), with a `data-scheme` attribute for light-specific rules.
- The language picker shows each language in its own script with a translated subtitle, and Traditional Chinese plus Japanese join Simplified Chinese and English.

- Internal layout: application assembly, collectors, retention, statistics routes, privacy routes, and connection routes now live in dedicated modules; the SQLite layer is split into schema, time-window, persistence, query, and server-registry modules with one shared database-path setting.
- Every playback write path goes through a single stats service that also invalidates the dashboard snapshot cache, so stale dashboard responses after writes are structurally prevented.
- Domain validation failures surface as HTTP 422 through one shared handler instead of per-route translations.
- Frontend pages load as ES modules sharing common HTTP, login-dialog, and preference modules; dashboard UI strings live in a catalog module guarded by Node unit tests against duplicate or missing translation keys.
- Pure frontend helpers (formatting, query building, custom-range validation) run under `npm run test:unit`.

- Release automation now runs only for `v*` tags and publishes the corresponding Docker image to Docker Hub.
- Documentation was consolidated around deployment, architecture, privacy, contributing, and security guidance.
- Dashboard styles and scripts are split into maintainable local assets; executable inline scripts are no longer permitted by the Content Security Policy.
- The API reference at `/docs` and `/redoc` is now rendered entirely from same-origin assets instead of CDN scripts blocked by the application policy.
- `POST /api/privacy/retention/apply` now requires `expected_retention_days` and returns `409` when the saved policy no longer matches the preview.
- Dashboard requests use latest-selection semantics, so changing the date, source, or ranking metric cancels stale work instead of rendering it under a newer filter.
- Connection settings now distinguish create and edit modes, display and edit each server's collection state, preserve saved passwords, and show the environment-backed fallback as read-only information.
- Finite retention policies are described and confirmed as automatic cleanup policies; “Apply now” remains a separate, policy-bound destructive action.
- The bundled Tailwind stylesheet was rebuilt from the current dashboard and settings templates.
- Import requests without a `Content-Length` header are limited while streaming and stop being consumed as soon as they exceed 5 MiB.

### Fixed

- Cancelling a server change while collectors were reconciling could leave the saved row in place; the rollback now completes before the cancellation propagates.

- Authentication handles non-ASCII token input as an authorization failure instead of a server error, and login forms clear submitted tokens after success.
- Unauthorized API responses retain security headers, and unauthorized imports are rejected before their request body is read.
- Logging in from the dashboard starts periodic refreshes, while an expired session stops refreshes and freezes the now-playing timer.
- Out-of-order statistics and now-playing responses can no longer overwrite results for newer filters.
- Destructive retention and per-user previews ignore stale responses; retention cleanup is rejected if the saved policy changed after preview.
- Source configuration fields are read and written atomically, and failed or cancelled collector reconciliation restores the previous saved fallback or server configuration.
- Late session checkpoints cannot reduce finalized state, listening duration, confidence, or session timestamps.
- Retention maintenance continues when collector initialization is degraded and is serialized with policy changes and manual cleanup.
- Server edits no longer silently create a duplicate connection, reactivate a disabled source, or misrepresent fallback credentials.
- Privacy imports are keyboard-accessible, reject files larger than 5 MiB before reading, and report both counted plays and short-play attempts.
- Collector teardown always closes clients and removes runtime state, including when a polling task has already failed.
- Persistence failures remain isolated from successful upstream polls, while tracker failures trigger the normal poll backoff.
- Empty replacement imports invalidate cached statistics, and malformed playback attempts return a validation error.
- Retention cleanup, daylight-saving-time date ranges, task health metrics, and client-name rendering are handled more reliably.
- The frontend build lockfile uses the patched `nanoid` release required by the current security advisory.
- A successful upstream response with no `nowPlaying` payload is treated as idle playback.
- The container smoke test uses an ephemeral loopback port by default instead of competing with a running service on port `39421`.

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

[Unreleased]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.3...HEAD
[0.8.3]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/StepaniaH/navidrome-stat/tree/v0.8.0
[0.7.0]: https://github.com/StepaniaH/navidrome-stat/tree/v0.7.0
[0.6.0]: https://github.com/StepaniaH/navidrome-stat/tree/v0.6.0
[0.5.4]: https://github.com/StepaniaH/navidrome-stat/tree/v0.5.4
[0.5.3]: https://github.com/StepaniaH/navidrome-stat/tree/v0.5.3
[0.5.2]: https://github.com/StepaniaH/navidrome-stat/tree/v0.5.2
[0.5.1]: https://github.com/StepaniaH/navidrome-stat/tree/v0.5.1
[0.5.0]: https://github.com/StepaniaH/navidrome-stat/tree/v0.5.0
