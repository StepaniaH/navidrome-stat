# Changelog

All notable user-facing changes are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Artist and album rankings now open a scoped detail drawer with playback and listening-time trends, first and latest play times, top tracks, recent plays, prior-period rank changes, and a stable shareable URL.

### Changed

- Client averages now include seconds, making similar minute-level values easier to compare.

### Fixed

- OpenSubsonic sessions no longer lose the playing intervals between sparse position reports, which could pin multi-minute client averages near the 30-second counting threshold.

## [0.8.8] - 2026-08-31

### Added

- Prometheus metrics now cover dashboard builds and cache outcomes, SQLite busy retries, imports, cover-art caching, and fixed-section query budgets.
- Recent Plays now offers on-demand details for attempts below the configured counting threshold. The details follow the current date, server, user, and timezone filters without labeling short sessions as intentional skips.
- Privacy export format v3 adds stable record IDs and fingerprints. Merge imports now report inserted, skipped, and conflicting rows; formats v1 and v2 remain importable and gain deterministic repeat-import deduplication.
- Readiness reports durable playback-write health separately from upstream polling health.

### Changed

- First-use dashboards keep connection guidance, current collection status, and playback-accounting details available while collapsing empty historical charts and tables. Filtered empty results still show section-specific guidance.
- Dashboard cache misses now read all local sections from one consistent SQLite snapshot. IANA-timezone bucket scans stream rows to reduce peak memory use.
- The product display name is consistently "Navidrome Stat" across the interface, documentation, API metadata, and releases. Existing repository and Docker image names remain unchanged.
- New local checkouts keep runtime data under `.data/`, while existing root-level databases remain automatically discoverable and Docker deployments continue using `/data`.
- Tag releases now require strict SemVer, matching source and Docker versions, release notes, the complete test workflow, and a container smoke test. Stable releases publish `latest`; prereleases do not. Successful image builds create a GitHub Release with the image digest and rollback guidance.
- Backup guidance archives the complete data volume and includes a restore integrity check before production recovery.
- Advanced theme settings summarize contrast by text role without exposing raw ratios, while retaining validation across every editable background.

### Fixed

- Cover-art caching preserves validated WebP and AVIF content types instead of defaulting unrecognized images to JPEG. The cache no longer writes unused MIME sidecar files.
- Cover-art proxy responses enforce a streaming size limit, verify the image signature, perform file operations off the event loop, and release per-key request locks after use.
- Retention previews no longer claim that `DELETE` shrinks the SQLite database file; they report deleted record payload while explaining that SQLite reuses freed pages internally.
- Older application versions now refuse databases with a newer schema before creating or changing schema objects and provide upgrade-or-restore guidance.
- Finite date-window queries now use schema v13 UTC epoch columns and source/user/time indexes instead of wrapping `played_at` in `datetime()`, allowing SQLite to use the time index while preserving local-calendar and DST boundaries.
- The Settings header distinguishes browser-only display preferences from connections and data controls saved by the service.
- Recent playback metadata is selected by playback time rather than insertion order, so importing older history cannot replace the latest title or timestamp.
- Album rankings persist upstream album IDs and keep same-named albums separate by source and artist; multi-server cover art uses each ranking row's source.
- Native `getSongHistory` imports commit and checkpoint each page, resume after limited batches or restarts, and retry failures with persisted exponential backoff.
- Deleting a user's data discards active in-memory sessions and suppresses their already queued writes while allowing future plays to start fresh sessions.
- Year-in-review links, requests, responses, cache entries, aggregates, and visible labels preserve year, server, user, and timezone scope; the page reports loading and retry states, prevents outdated responses from replacing the selected year, and provides text summaries for charts.
- The review login dialog keeps keyboard focus within the dialog, the dashboard localizes its review link, and recent-play column preferences apply on mobile.
- The recent-play column menu remains visible outside short empty-state cards and stays open while multiple columns are changed.
- Playback-attempt rates now exclude backfill and native-history imports because those records do not represent live sessions collected by the application. Privacy-archive restores remain included.
- A cache invalidation error after a successful playback write is logged separately and no longer marks durable playback persistence as unhealthy.

### Security

- Docker build contexts exclude local credential keys, databases, cover-art caches, backups, and `.data/` contents.
- Metrics use fixed section labels and do not include users, servers, tracks, or other high-cardinality identifiers.

## [0.8.7] - 2026-08-29

### Added

- The connection settings page now gives first-use guidance and authenticated, redacted diagnostic states for unconfigured, disabled, starting, authentication, TLS, timeout, network, upstream, collector, and connected-without-history conditions.
- Advanced theme settings now show each contrast pair, copy individual HEX values, guard unsaved previews, and import or export a strict versioned JSON document for the selected preset.
- The synthetic statistics benchmark supports multiple history sizes, filtered summary and history scenarios, query-plan checks, JSON output, and optional per-query time budgets.

### Changed

- Connection and appearance behavior now live in dedicated frontend modules; the settings entry point retains authentication, tabs, privacy composition, and page-level localization.
- Dashboard empty states distinguish an installation with no history from a date, server, or user filter that has no matches.

### Security

- Connection test and collector failures expose stable diagnostic categories instead of raw upstream exception text. The aggregate diagnostics endpoint requires the same authentication as the dashboard API and omits connection identities and credentials.
- The published container disables Uvicorn request access logs so dashboard filters, source identifiers, and usernames in application URLs are not written to container logs.

## [0.8.6] - 2026-08-29

### Added

- Every palette family now has matching light and dark variants. Advanced theme settings support browser-local overrides for six core colors per concrete preset, with preview, cancel, preset restoration, and 4.5:1 contrast validation.

### Fixed

- Pie-chart seams now blend with the active surface, while chart tooltips use theme-aware soft borders and ambient shadows instead of ECharts' fixed black shadow.
- Historical dashboard and year-in-review data remain available when optional album-art enrichment cannot reach or authenticate to a saved server.

## [0.8.5] - 2026-08-29

### Changed

- Theme selection now separates system, dark, and light modes from nine palette families. Thirteen concrete variants share one resolver and one set of theme tokens across the dashboard, year-in-review, settings, and API reference.
- Built-in, Gruvbox, Catppuccin, and Solarized include matching light and dark variants; dark-only palettes are clearly unavailable in light mode instead of applying an unsuitable color scheme.
- Existing browser theme preferences remain compatible, while new mode and palette choices continue to stay in the browser. Theme surfaces, text, controls, and charts now use the same semantic colors on every page.

## [0.8.4] - 2026-08-27

### Added

- Optional backfill bridge: point any saved server at a Navidrome smart playlist and its watched contents are imported as estimated pre-install listens through the public `getPlaylist` API only. One estimated event per track derives from the exact last-played timestamp; re-runs never double count, and events inside live-poller coverage are excluded. Configure per connection on the settings page, watch continuously, or trigger a one-off sync from the API.
- A `getSongHistory` importer is wired end to end: once upstream Navidrome ships the proposed endpoint (PR #5650), an initial native-history import runs automatically when the server advertises it.
- Top-artist lists now show cover art when Navidrome provides an artist image: collected sessions persist the upstream artist ID, and the dashboard and year-in-review rankings resolve artwork through the authenticated cover-art proxy with the usual letter-tile fallback.
- Spanish and French interface localization across the dashboard, review, and settings pages; all languages now label one another in the settings picker.

### Changed

- With the OpenSubsonic `playbackReport` extension, a terminal `stopped` or `expired` entry finalizes its session immediately instead of lingering through the pause grace window, so ended tracks no longer inflate active-session counts.
- Reconciling collectors logs a single warning when `NAVIDROME_*` environment variables are set but ignored because saved server connections exist.
- Review-page aggregation moved to a dedicated query module and year-in-review restore paths are covered by repeatable migration fixtures and export/import round-trip checks (internal test coverage; no behavior change).

### Security

- Saved Navidrome credentials (server connections and the saved fallback password) are encrypted at rest with AES-256-GCM using a per-installation key file, `secret.key`, generated beside the SQLite database. Startup migration re-wraps previously stored plaintext once. Back up the key file together with the database; restoring a database without it leaves saved passwords unrecoverable by design.

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

[Unreleased]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.8...HEAD
[0.8.8]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.7...v0.8.8
[0.8.7]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.6...v0.8.7
[0.8.6]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.5...v0.8.6
[0.8.5]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.4...v0.8.5
[0.8.4]: https://github.com/StepaniaH/navidrome-stat/compare/v0.8.3...v0.8.4
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
