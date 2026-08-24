# Compatibility policy (pre-1.0)

Navidrome Statistic has not reached 1.0. This page records what you can rely on between releases today, and what will be stabilized at 1.0.

## Stable today

- **SQLite schema migrations** only move forward, run automatically at startup, and never rewrite or drop existing listening data. Downgrades across schema versions are not supported; back up the database before updating a pinned version.
- **Privacy export format** `format_version: 2` stays readable by later releases; importers continue to accept every format listed in `SUPPORTED_IMPORT_FORMAT_VERSIONS`.
- **Environment variables** documented in the README keep their names, defaults, and clamping bounds.
- **Dashboard and settings data APIs** (`/api/stats/*`, `/api/privacy/*`, `/api/servers/*`, `/api/source/*`) add fields only in additive ways: new response fields are optional or nullable, and no field is removed or repurposed without a changelog entry.
- **Health endpoints** (`/health`, `/health/ready`) keep their top-level `status` values (`ok`, `degraded`, `not_ready`) and check names.
- **Prometheus metrics** on `/metrics` keep existing metric names and types; new series may appear.

## Not yet stable

- Any HTTP endpoint may gain new required query semantics only behind a documented default (for example, `year` defaulting to the current year on `/api/stats/review`).
- The frontend asset layout under `src/static/` (including `js/` module boundaries) may change between releases; the pages and their URLs are the interface.
- The cover-art disk cache directory layout is an implementation detail; treat it as disposable.

## At 1.0

All `/api/*` request and response schemas documented by `/openapi.json`, the privacy export format, the SQLite migration history, and the environment contract become semver-stable. Breaking changes then require a major version and a documented migration path.
