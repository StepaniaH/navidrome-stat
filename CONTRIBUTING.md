# Contributing

English is the default language for issues, pull requests, and commit messages. User-facing documentation is bilingual: keep [`README.md`](README.md) and [`README.zh-CN.md`](README.zh-CN.md) aligned when you change install or runtime behavior.

## Privacy first

Do not commit, paste, or screenshot any of the following:

- Real `NAVIDROME_URL`, usernames, passwords, tokens, cookies, or `.env` files
- Real SQLite databases, WAL/SHM files, backups, or export JSON from a live deployment
- Access logs or proxy logs that include Subsonic `t` / `s` query parameters
- Play history, track titles, artist names, or client names from a real library

Tests and docs must use obvious placeholders such as `http://navidrome.example.invalid:4533` and `example_user`. If a report needs logs, redact them first. Security-sensitive reports belong in [GitHub Security Advisories](SECURITY.md), not a public issue.

## Development setup

Python 3.11 is the supported runtime (CI and the production Dockerfile).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest -q --cov=src --cov-report=term-missing --cov-fail-under=80
```

Frontend assets and synthetic browser tests:

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

Do not point the development server at a production Navidrome account unless the repository owner explicitly asked you to, and never copy that environment into the repo.

## What to change

- Read [`docs/current-state.md`](docs/current-state.md) before assuming README text is the implementation.
- Executable follow-up work lives only in [`docs/tasks.md`](docs/tasks.md). Do not add a second roadmap or TODO list.
- HTTP, Subsonic, environment variable, or SQLite schema changes must update [`docs/interfaces.md`](docs/interfaces.md) in the same change.
- Privacy or logging changes must update [`docs/privacy.md`](docs/privacy.md).
- User-visible install steps must update both READMEs.

## Pull requests

1. Keep the diff scoped to one task or one defect.
2. Include tests for behavior changes. Browser tests must keep using synthetic fixtures.
3. Run the commands above plus `python3 scripts/check_md_links.py` and `git diff --check`.
4. Fill the pull request template. Do not include real hostnames or credentials in the description.

Maintainers may rewrite or split agent-produced patches so they match these rules.
