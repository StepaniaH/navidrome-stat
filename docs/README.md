# Documentation

[简体中文](README.zh-CN.md) · [Project overview](../README.md)

## Install and run

- [Docker deployment](deployment.md): install a published image, connect servers, and persist data.
- [Configuration reference](configuration.md): environment variables, defaults, and access tokens.
- [Operations](operations.md): update, back up, restore, and diagnose problems.

## Use your listening data

- [Using the dashboard](usage.md): filters, rankings, details, Listening Review, and appearance.
- [Collection and counting](collection.md): play thresholds, duration quality, history backfill, and ListenBrainz ingestion.
- [Artist attribution](artist-attribution.md): combined and separate collaboration credits.
- [Charts and detail views](data-relations.md): grouping, comparison periods, and shared scope.
- [Privacy](privacy.md): stored data, retention, archives, credentials, and browser behavior.

## Project reference

- [Compatibility policy](compat.md)
- [Changelog](../CHANGELOG.md)
- [Security policy](../SECURITY.md)
- [Contributing](../CONTRIBUTING.md)
- [Adding an interface language](translations.md)

The running application serves its searchable API reference at `/docs` (also `/redoc`) and its schema at `/openapi.json`. These routes require administrator access when authentication is enabled and can be disabled with `OPENAPI_ENABLED=false`.
