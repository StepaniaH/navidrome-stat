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

For frontend assets and browser tests:

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

## Making changes

- Keep each change focused and add tests for changed behavior.
- Update both READMEs when user-facing setup or configuration changes.
- Update [`docs/architecture.md`](docs/architecture.md) when the system design or data flow changes.
- Update [`docs/privacy.md`](docs/privacy.md) when stored data, logging, retention, export, or authentication behavior changes.
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
