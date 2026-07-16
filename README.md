# Navidrome Statistic

> 本文档保留项目概览与快速启动说明。项目事实、稳定接口、隐私确认和后续任务请从 [AGENTS.md](AGENTS.md) 与 [docs/README.md](docs/README.md) 进入。

> 🤖 **Built with Vibe Coding**: This entire project, from design specs to backend logic and frontend UI, was generated and orchestrated entirely through AI (Gemini CLI) in an autonomous "Vibe Coding" workflow. 

Navidrome Statistic is a lightweight, standalone monitoring and analytics dashboard designed specifically for [Navidrome](https://www.navidrome.org/) music servers.

It runs as a background service, passively monitoring your Navidrome server's Subsonic API to keep an accurate count of your song plays. It features an integrated web dashboard to visualize your listening habits, client distribution, and transcoding ratios.

## Features

- **Zero-Friction Tracking**: Uses an intelligent in-memory state machine to track listening sessions. A song is only counted as a "Play" if you listen to it for more than 30 seconds.
- **Client & Transcoding Stats**: Automatically records which app/client you are using (e.g., Amperfy, Feishin) and whether the stream is being transcoded.
- **Built-in Dashboard**: A clean, responsive single-page visual dashboard built with TailwindCSS and ECharts.
- **Lightweight**: Written in Async Python (FastAPI + SQLite), resulting in minimal CPU/RAM footprint.

## Quick Start (Docker)

The easiest way to run Navidrome Statistic is via Docker Compose.

1. Create a `docker-compose.yml` and a `.env` file in your desired directory.

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  navidrome-statistic:
    build: . # Or use the docker image once published
    container_name: navidrome-statistic
    restart: unless-stopped
    ports:
      - "39421:39421"
    env_file:
      - .env
    volumes:
      - ./navidrome_stats.db:/app/navidrome_stats.db
```

**.env:**
```env
# Your Navidrome Server URL (do not include trailing slash)
NAVIDROME_URL=http://your-navidrome-server:4533
# A valid Navidrome username
NAVIDROME_USER=your_username
# The password for the Navidrome user
NAVIDROME_PASS=your_password
# Polling interval in seconds (Default: 10)
POLL_INTERVAL=10
# The internal database location
DATABASE_URL=/app/navidrome_stats.db
```

2. Start the service:
```bash
docker-compose up -d
```

3. Visit your dashboard at `http://localhost:39421`.

## How It Works

Unlike standard Subsonic API `getNowPlaying` polling which can hammer the database and create duplicate entries, this service uses an **Event-Driven State Machine**:
1. It polls the server every 10 seconds.
2. When a track starts, it registers a session in memory.
3. It silently updates the session time without writing to the disk.
4. When the track changes or stops, it calculates the total duration. If the duration exceeds 30 seconds, it writes exactly **one** record to the SQLite database.

## Development

If you wish to run it locally without Docker:

```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

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
