# Navidrome Statistic

> 本文档保留项目概览与快速启动说明。项目事实、稳定接口、隐私确认和后续任务请从 [AGENTS.md](AGENTS.md) 与 [docs/README.md](docs/README.md) 进入。

> 🤖 **Built with Vibe Coding**: This entire project, from design specs to backend logic and frontend UI, was generated and orchestrated entirely through AI (Gemini CLI) in an autonomous "Vibe Coding" workflow. 

Navidrome Statistic is a lightweight, standalone monitoring and analytics dashboard designed specifically for [Navidrome](https://www.navidrome.org/) music servers.

It runs as a background service, passively monitoring your Navidrome server's Subsonic API to keep an accurate count of your song plays. It features an integrated web dashboard to visualize your listening habits, client distribution, and transcoding ratios.

## Features

- **Zero-Friction Tracking**: Polls Navidrome `getNowPlaying` and tracks listening sessions in memory. A song counts as one play once it has been observed for **at least 30 seconds** (`>= 30`); the write happens during playback, not only after a track ends.
- **Repeat Plays**: Listening to the same track again adds another row and increases aggregated play counts.
- **Client & Transcoding Stats**: Records which app/client you are using (e.g., Amperfy, Feishin) and whether the stream is being transcoded.
- **Privacy Controls**: Default **permanent** retention with a settings page (`/settings`) to choose 1–360 days or permanent; per-user JSON export/import and deletion with preview-before-confirm.
- **Built-in Dashboard**: A responsive single-page dashboard built with TailwindCSS and ECharts (loaded from public CDNs).
- **Lightweight**: Async Python (FastAPI + SQLite) with a small CPU/RAM footprint.

## Quick Start (Docker)

The easiest way to run Navidrome Statistic is via Docker Compose. The example below matches this repository's [`docker-compose.yml`](docker-compose.yml) service name (`navidrome-stat`).

1. Clone the repository and create a `.env` file in the project root (never commit it).

**docker-compose.yml** (already in the repo):

```yaml
services:
  navidrome-stat:
    build: .
    container_name: navidrome-stat
    ports:
      - "39421:39421"
    volumes:
      - ./navidrome_stats.db:/app/navidrome_stats.db
    environment:
      NAVIDROME_URL: ${NAVIDROME_URL:-http://navidrome.example.invalid:4533}
      NAVIDROME_USER: ${NAVIDROME_USER:-example_user}
      NAVIDROME_PASS: ${NAVIDROME_PASS:-placeholder_pass}
      POLL_INTERVAL: ${POLL_INTERVAL:-10}
      DATABASE_URL: ${DATABASE_URL:-/app/navidrome_stats.db}
      STATS_API_TOKEN: ${STATS_API_TOKEN:-}
    restart: unless-stopped
```

Compose reads a local `.env` for `${VAR}` substitution when present; CI validates config without that file.

**.env** (placeholders only):

```env
NAVIDROME_URL=http://navidrome.example.invalid:4533
NAVIDROME_USER=example_user
NAVIDROME_PASS=<set-in-runtime-environment>
POLL_INTERVAL=10
DATABASE_URL=/app/navidrome_stats.db
# Optional: protect dashboard and stats APIs (recommended if not behind a reverse proxy)
STATS_API_TOKEN=<set-in-runtime-environment>
```

2. Start the service:

```bash
docker compose up -d
```

3. Visit the dashboard at `http://localhost:39421`. Open **隐私设置** (`/settings`) to manage retention and per-user data.

## Privacy & Data Control

- **Default**: play history is kept **permanently** until you change the policy.
- **Retention**: use `/settings` to set 1–360 days or switch back to permanent. The UI shows how many records would be removed before you confirm cleanup.
- **Export / import**: download a user's play history as JSON, or import it back (merge or replace).
- **Delete**: remove all records for a selected user after preview and confirmation.
- **Your responsibility**: ensure Navidrome users are informed that listening activity is being collected. Set `STATS_API_TOKEN` if the service is reachable beyond a trusted network.

See [`docs/privacy.md`](docs/privacy.md) and [`docs/security.md`](docs/security.md) for full boundaries.

## How It Works

This service uses **timed polling** plus an **in-memory session tracker** (not push events from Navidrome):

1. On startup it polls `getNowPlaying` every `POLL_INTERVAL` seconds (default **10**).
2. When a player and track are seen, a session is stored in memory and updated on each poll.
3. Once the observed listen time reaches **30 seconds or more**, **one** row is written to SQLite for that session. The same session is not written twice.
4. When the track changes or the player disappears, the in-memory session is cleared. Short listens under 30 seconds are discarded.
5. The dashboard refreshes every **10 seconds** and reads aggregated stats from the local database.

**Caveats**

- Reported listen duration is **observed wall-clock time** between polls, not exact player position.
- The service has **optional authentication** via `STATS_API_TOKEN`. Without it, do not expose the service to untrusted networks; use a reverse proxy or set the token.
- Playback metadata is stored in plaintext SQLite on disk.

## Development

If you wish to run it locally without Docker:

```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt

# Run the server
uvicorn src.main:app --host 0.0.0.0 --port 39421
```

### Dependencies

- `requirements.txt` — pinned direct runtime packages.
- `requirements.lock` — full transitive runtime lock used by Docker.
- `requirements-dev.txt` — runtime + pinned test tools.

To upgrade a runtime dependency:

```bash
# 1. Edit the version pin in requirements.txt
# 2. Regenerate the lock file
bash scripts/refresh_requirements_lock.sh
# 3. Reinstall and test
pip install -r requirements-dev.txt
pytest -q
```

## Project Documentation

- [Agent 工作入口](AGENTS.md)
- [文档索引](docs/README.md)
- [当前实现事实](docs/current-state.md)
- [稳定接口登记](docs/interfaces.md)
- [隐私与敏感信息确认](docs/privacy.md)
- [安全与部署边界](docs/security.md)
- [后续任务列表](docs/tasks.md)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
