# Contributing

Contributions are welcome. Before opening an issue or pull request, search the existing issues to avoid duplicates.

English is used for issues, pull requests, and commit messages. User-facing documentation is bilingual, so changes to installation, configuration, or runtime behavior should update both [`README.md`](README.md) and [`README.zh-CN.md`](README.zh-CN.md).

## Development setup

Navidrome Statistic uses Python 3.11.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Run the backend checks from the repository root:

```bash
ruff check .
pytest -q --cov=src --cov-report=term-missing --cov-fail-under=80
```

Frontend assets and browser tests use Node.js:

```bash
npm ci
npm run test:unit
npm run build:assets
npx playwright install chromium
npm run test:e2e
```

`npm run test:e2e` rebuilds the bundled assets before running Playwright. Commit updated files under `src/static/vendor/` when an asset dependency, the Tailwind input, or utility classes in the dashboard HTML or JavaScript change.

## Maintenance tools

Run the synthetic statistics benchmark after changing aggregate queries, indexes, or dashboard caching:

```bash
python3 scripts/benchmark_stats.py --sizes 100000,1000000
```

The report measures all-history time buckets plus source-and-user-filtered summary and history queries, and verifies the filtered history query plan. Use `--json` for machine-readable output and `--max-query-ms <budget>` when a stable CI host has an agreed performance budget. The older `--rows` single-size option remains available for compatibility.

Run the container smoke test after changing the Dockerfile, runtime dependencies, startup behavior, or health endpoints. It requires Docker and uses an ephemeral loopback port by default. Set `SMOKE_HOST_PORT` only when a fixed host port is needed.

```bash
scripts/docker_smoke_test.sh
```

Runtime dependency changes must update both `requirements.txt` and `requirements.lock`. The refresh script creates a clean Python 3.11 environment, verifies the resolved dependencies, and atomically replaces the lock file:

```bash
scripts/refresh_requirements_lock.sh
```

If `python3.11` is not on `PATH`, provide its executable explicitly:

```bash
PYTHON_BIN=/path/to/python3.11 scripts/refresh_requirements_lock.sh
```

Review the complete lock-file diff and rerun the backend checks after refreshing it.

## Making changes

- Keep each change focused and add tests for changed behavior.
- Update both READMEs when user-facing setup or configuration changes.
- Update [`docs/architecture.md`](docs/architecture.md) when the system design or data flow changes.
- Update [`docs/privacy.md`](docs/privacy.md) when stored data, logging, retention, export, or authentication behavior changes.
- Update [`docs/roadmap.md`](docs/roadmap.md) only when broad project direction or a stated non-goal changes.
- Run `python3 scripts/check_md_links.py` after editing Markdown files.

## Privacy

Do not include real server URLs, usernames, passwords, tokens, cookies, `.env` files, databases, backups, logs, or listening history in issues, tests, documentation, or pull requests. Subsonic request URLs may contain authentication query parameters and must be redacted.

Use clearly fictional values such as `http://navidrome.example.invalid:4533` and `example_user`. Report security vulnerabilities through the private process described in [`SECURITY.md`](SECURITY.md).

## Pull requests

A pull request should include:

- A concise description of the problem and the change
- Tests for behavior changes, using synthetic fixtures
- The commands used to verify the change and their results
- Documentation updates where applicable

Before submitting, run:

```bash
python3 scripts/check_md_links.py
git diff --check
```

## Maintainer releases

Releases are tag-only: pushing a `v*` tag starts the Docker workflow. The workflow publishes `stepaniah/navidrome-statistic:<tag>` and updates `stepaniah/navidrome-statistic:latest`; it does not create a GitHub Release.

Before tagging:

1. Move the release notes from `Unreleased` to a versioned, dated section in `CHANGELOG.md`.
2. Verify the version on a clean `main` checkout with the backend checks, browser tests, Markdown link checker, and container smoke test.
3. Confirm that the repository has valid `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets.
4. Create and push an annotated semantic-version tag:

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

5. Verify that the Docker Hub manifest contains both `linux/amd64` and `linux/arm64`, then confirm `/api/about` reports the expected version from the published image.

Every matching tag also moves `latest`, so only tag a prerelease when that behavior is intended. Do not move or reuse a published tag. To roll back, deploy a previously published version tag rather than `latest`.
