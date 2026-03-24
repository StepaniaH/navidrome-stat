# Navidrome Statistic Implementation Plan (Rev 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the polling logic to use an in-memory session state machine to count actual "Plays" instead of saving DB snapshots every 10 seconds.

---

### Task 1: Refactor Database Schema

**Files:**
- Modify: `public/navidrome-statistic/src/database.py`

- [ ] **Step 1: Update Table Schema**
Change `playback_snapshots` to `play_history` with fields: `played_at`, `username`, `client_name`, `track_id`, `title`, `artist`, `album`, `is_transcoding`, `listen_duration_sec`. Add logic to drop the old table or just rely on a clean DB for the rewrite.

- [ ] **Step 2: Refactor `save_snapshot` to `save_play_session`**
Insert a single record into `play_history` representing one completed listen.

- [ ] **Step 3: Update Analytics Queries**
Update `get_player_stats`, `get_transcoding_stats`, and `get_playback_history` to query `play_history`. 

---

### Task 2: Implement Memory State Machine in Polling Loop

**Files:**
- Modify: `public/navidrome-statistic/src/main.py`

- [ ] **Step 1: Define Session Data Structure**
Create a global `active_sessions = {}` dict to store current playback info for each `player_id`.

- [ ] **Step 2: Implement Session Tracking Logic**
In `polling_loop()`:
1. Fetch `getNowPlaying`.
2. Compare playing tracks against `active_sessions`.
3. If a track is new for a player, save the old session if duration > 30s. Start a new session.
4. If a track is the same, update `last_seen_at`.
5. Implement garbage collection: find sessions not updated in the last 30s, save them if valid, and remove them from memory.

---

### Task 3: Update Frontend Dashboard

**Files:**
- Modify: `public/navidrome-statistic/src/static/index.html`

- [ ] **Step 1: Revert Table Headers**
Change "Listen Time" back to "Plays" since the API will now return actual play counts again.

---

### Task 4: Testing & Verification

- [ ] **Step 1: Fix existing tests**
Update `test_database.py` and `test_main.py` to reflect the schema and logic changes.
- [ ] **Step 2: Local validation**
Start service locally and observe terminal logs to ensure session state machine successfully catches a track change and inserts exactly ONE record.