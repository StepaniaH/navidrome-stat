---
date: "2026-03-23T10:00:00+08:00"
type: "design-spec"
tags: [navidrome, python, fastapi, sqlite, monitoring]
---

# Navidrome Statistic Service Design Spec

## 1. Project Overview
A standalone monitoring and analytics dashboard for Navidrome music servers. It polls the Subsonic API to track real-time playback status, persists data into SQLite, and provides statistical insights via a web interface.

## 2. Core Architecture (Approach A: Async Monolith)
The service will run as a single Python process using FastAPI.
- **Web Engine**: FastAPI for REST API and static file serving.
- **Background Poller**: An `asyncio` task started at application startup to poll Navidrome every 10 seconds.
- **Database**: SQLite with `aiosqlite` for non-blocking I/O.
- **HTTP Client**: `httpx` for asynchronous Subsonic API requests.

## 3. Data Model (SQLite Schema)

### `playback_snapshots` Table
Records the instantaneous state of every active player during each poll.
- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `timestamp`: DATETIME (Default: CURRENT_TIMESTAMP)
- `username`: TEXT (Navidrome user)
- `player_id`: TEXT (Unique ID for the player session)
- `client_name`: TEXT (e.g., "Feishin", "Strawberry", "Web Player")
- `track_id`: TEXT (Subsonic ID of the track)
- `title`: TEXT
- `artist`: TEXT
- `album`: TEXT
- `is_transcoding`: BOOLEAN (True if `current_bitrate` < `original_bitrate`)
- `original_bitrate`: INTEGER (kbps)
- `current_bitrate`: INTEGER (kbps)
- `position_ms`: INTEGER (Current playback progress)
- `player_state`: TEXT (playing, paused, buffered)

## 4. Key Logic & Algorithms

### 4.1. Polling & Authentication
- Read `NAVIDROME_URL`, `USER`, `PASS` from `.env`.
- Generate Subsonic Auth (MD5 salt + token) per request.
- Endpoint: `getNowPlaying.view?u={user}&t={token}&s={salt}&v=1.16.1&c=navidrome-stat&f=json`.

### 4.2. Transcoding Detection (Heuristic Comparison)
- Compare `bitRate` (current) from the now-playing entry with the track's metadata `bitRate` (original).
- If original metadata is missing, fallback to common bitrate thresholds (e.g., > 320kbps is likely original/lossless).

### 4.3. Data Deduplication
- Before inserting a snapshot, check if the `(player_id, track_id, position_ms)` is identical to the last recorded snapshot for that player to prevent redundant writes if the player is paused or the API returns cached data.

### 4.4. Statistical Aggregation (API Endpoints)
- `/api/stats/players`: Distribution of client usage.
- `/api/stats/transcoding`: Ratio of transcoded vs direct play.
- `/api/stats/history`: Top tracks and total listening time per user.

## 5. Security & Environment
- **Environment Variables**: Managed via `.env` (excluded from Git).
- **Database**: `navidrome_stat.db` (excluded from Git).
- **Containerization**: Single Docker image with external volume mounts for DB.

## 6. Development Stages
1. **Stage 1**: API connectivity & Auth testing.
2. **Stage 2**: SQLite integration & Poller implementation.
3. **Stage 3**: Analytics logic & REST API development.
4. **Stage 4**: Frontend UI implementation.
5. **Stage 5**: Dockerization & final cleanup.
