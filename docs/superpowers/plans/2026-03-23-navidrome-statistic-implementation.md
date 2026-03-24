# Navidrome Statistic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a monitoring and analytics service for Navidrome that polls Subsonic API, stores snapshots in SQLite, and provides a web dashboard.

**Architecture:** An asynchronous Python monolith using FastAPI. A background `asyncio` task polls the Navidrome server every 10 seconds and saves the playback state to a SQLite database.

**Tech Stack:** Python 3.11+, FastAPI, httpx, aiosqlite, Docker.

---

### Task 1: Project Setup & Environment

**Files:**
- Create: `public/navidrome-statistic/.env`
- Create: `public/navidrome-statistic/.gitignore`
- Create: `public/navidrome-statistic/requirements.txt`

- [ ] **Step 1: Create .env template**
```env
NAVIDROME_URL=http://localhost:4533
NAVIDROME_USER=admin
NAVIDROME_PASS=password
POLL_INTERVAL=10
```

- [ ] **Step 2: Create .gitignore**
```text
.venv/
__pycache__/
*.db
.env
```

- [ ] **Step 3: Create requirements.txt**
```text
fastapi
uvicorn
httpx
aiosqlite
python-dotenv
```

- [ ] **Step 4: Initialize virtual environment**
Run: `python -m venv .venv && source .venv/bin/bin/activate && pip install -r requirements.txt`

---

### Task 2: Subsonic API Client & Authentication

**Files:**
- Create: `public/navidrome-statistic/src/client.py`
- Test: `public/navidrome-statistic/tests/test_client.py`

- [ ] **Step 1: Write failing test for auth token generation**
```python
from src.client import generate_auth
def test_generate_auth():
    token, salt = generate_auth("password")
    assert len(token) == 32
    assert len(salt) == 6
```

- [ ] **Step 2: Implement `generate_auth` in `src/client.py`**
```python
import hashlib
import secrets
import string

def generate_auth(password: str):
    salt = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
    token = hashlib.md5((password + salt).encode()).hexdigest()
    return token, salt
```

- [ ] **Step 3: Implement API client to fetch `getNowPlaying`**
Implement `NavidromeClient` class with `get_now_playing()` method using `httpx`.

---

### Task 3: Database Schema & Connection

**Files:**
- Create: `public/navidrome-statistic/src/database.py`
- Test: `public/navidrome-statistic/tests/test_database.py`

- [ ] **Step 1: Define Table Schema and initialization logic**
Use `aiosqlite` to create `playback_snapshots` table as defined in the spec.

- [ ] **Step 2: Implement `save_snapshot` function**
Function to insert data into the table.

---

### Task 4: Background Poller & FastAPI Integration

**Files:**
- Create: `public/navidrome-statistic/src/main.py`

- [ ] **Step 1: Setup FastAPI app and lifespan events**
Initialize database and start the background polling task using `asyncio.create_task`.

- [ ] **Step 2: Implement the polling loop**
Loop every `POLL_INTERVAL` seconds, fetch data, and save to DB.

---

### Task 5: Analytics API Endpoints

**Files:**
- Modify: `public/navidrome-statistic/src/main.py`

- [ ] **Step 1: Implement `/api/stats/players`**
SQL query to count occurrences of `client_name`.

- [ ] **Step 2: Implement `/api/stats/transcoding`**
SQL query to calculate `is_transcoding` ratio.

---

### Task 6: Dockerization

**Files:**
- Create: `public/navidrome-statistic/Dockerfile`
- Create: `public/navidrome-statistic/docker-compose.yml`

- [ ] **Step 1: Write Dockerfile**
Use `python:3.11-slim`.

- [ ] **Step 2: Write docker-compose.yml**
Define service and volume for the SQLite database.
