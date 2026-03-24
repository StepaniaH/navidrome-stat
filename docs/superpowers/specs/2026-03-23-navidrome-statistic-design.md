---
date: "2026-03-23T10:00:00+08:00"
type: "design-spec"
tags: [navidrome, python, fastapi, sqlite, monitoring]
---

# Navidrome Statistic Service Design Spec (Rev 2: Session-based Play Counting)

## 1. Project Overview
A standalone monitoring and analytics dashboard for Navidrome music servers. It polls the Subsonic API to track real-time playback status, persists completed playback sessions into SQLite, and provides statistical insights via a web interface.

## 2. Core Architecture
The service will run as a single Python process using FastAPI.
- **Web Engine**: FastAPI for REST API and static file serving.
- **Background Poller**: An `asyncio` task to poll Navidrome every 10 seconds.
- **State Machine**: In-memory dictionary tracking active playback sessions to aggregate 10s snapshots into singular "Play" events.
- **Database**: SQLite with `aiosqlite` for non-blocking I/O.
- **HTTP Client**: `httpx` for asynchronous Subsonic API requests with connection pooling.

## 3. Data Model (SQLite Schema)

### `play_history` Table (Refactored from playback_snapshots)
Records completed play events (one row per song listened).
- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `played_at`: DATETIME (When the track finished/changed)
- `username`: TEXT 
- `client_name`: TEXT 
- `track_id`: TEXT 
- `title`: TEXT
- `artist`: TEXT
- `album`: TEXT
- `is_transcoding`: INTEGER (Boolean)
- `listen_duration_sec`: INTEGER (How long it was listened to)

## 4. Key Logic & Algorithms

### 4.1. Polling & Authentication
- Read `NAVIDROME_URL`, `USER`, `PASS` from `.env`.
- Endpoint: `getNowPlaying.view?u={user}&t={token}&s={salt}&v=1.16.1&c=navidrome-stat&f=json`.

### 4.2. In-Memory Session Tracking (The Play Counter)
To avoid spamming the DB and to count actual "Plays" rather than "Seconds":
- A dictionary `active_sessions` mapping `player_id` -> `SessionData`.
- On each poll:
  - If a track is playing: update `last_seen_at` in memory.
  - If a track changes for a player: finalize the old session. If `duration > 30s`, save it to the DB as 1 play. Start a new session for the new track.
  - Periodic cleanup: Identify players not seen in the last 30 seconds and finalize their sessions.

### 4.3. Statistical Aggregation (API Endpoints)
- `/api/stats/players`: Distribution of client usage (Count of play events).
- `/api/stats/transcoding`: Ratio of transcoded vs direct play.
- `/api/stats/history`: Top tracks, showing play counts.