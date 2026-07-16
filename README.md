# Navidrome Statistic

> 本文档保留项目概览与快速启动说明。项目事实、稳定接口、隐私确认和后续任务请从 [AGENTS.md](AGENTS.md) 与 [docs/README.md](docs/README.md) 进入。

> 🤖 **Built with Vibe Coding**: This entire project, from design specs to backend logic and frontend UI, was generated and orchestrated entirely through AI (Gemini CLI) in an autonomous "Vibe Coding" workflow. 

Navidrome Statistic is a lightweight, standalone monitoring and analytics dashboard designed specifically for [Navidrome](https://www.navidrome.org/) music servers.

It runs as a background service, passively monitoring your Navidrome server's Subsonic API to keep an accurate count of your song plays. It features an integrated web dashboard to visualize your listening habits, client distribution, and transcoding ratios.

## Features

- **Zero-Friction Tracking**: Polls Navidrome `getNowPlaying` and tracks listening sessions in memory. A song counts as one play once it has been observed for **at least 30 seconds** (`>= 30`); the write happens during playback, not only after a track ends.
- **Repeat Plays**: Listening to the same track again adds another row and increases aggregated play counts.
- **Client & Transcoding Stats**: Records which app/client you are using (e.g., Amperfy, Feishin) and whether the stream is being transcoded.
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
    env_file:
      - .env
    restart: unless-stopped
```

**.env** (placeholders only):

```env
NAVIDROME_URL=http://navidrome.example.invalid:4533
NAVIDROME_USER=example_user
NAVIDROME_PASS=<set-in-runtime-environment>
POLL_INTERVAL=10
DATABASE_URL=/app/navidrome_stats.db
```

2. Start the service:

```bash
docker compose up -d
```

3. Visit the dashboard at `http://localhost:39421`.

## How It Works

This service uses **timed polling** plus an **in-memory session tracker** (not push events from Navidrome):

1. On startup it polls `getNowPlaying` every `POLL_INTERVAL` seconds (default **10**).
2. When a player and track are seen, a session is stored in memory and updated on each poll.
3. Once the observed listen time reaches **30 seconds or more**, **one** row is written to SQLite for that session. The same session is not written twice.
4. When the track changes or the player disappears, the in-memory session is cleared. Short listens under 30 seconds are discarded.
5. The dashboard refreshes every **10 seconds** and reads aggregated stats from the local database.

**Caveats**

- Reported listen duration is **observed wall-clock time** between polls, not exact player position.
- The service has **no built-in authentication**; do not expose it to untrusted networks without a reverse proxy or other access control.
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

## Project Documentation

- [Agent 工作入口](AGENTS.md)
- [文档索引](docs/README.md)
- [当前实现事实](docs/current-state.md)
- [稳定接口登记](docs/interfaces.md)
- [隐私与敏感信息确认](docs/privacy.md)
- [后续任务列表](docs/tasks.md)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
