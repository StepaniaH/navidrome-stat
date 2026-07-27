# README and Now Playing Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore truthful multi-server now-playing output and replace the mixed root README with separate, privacy-conscious English and Chinese operator guides.

**Architecture:** Keep per-server `PlaybackSessionTracker` instances as the owners of live playback state and expose them through one module-level runtime registry. All live-session readers aggregate a registry snapshot, exclude paused sessions, and fall back to the existing global tracker for direct consumers. Documentation uses the published Docker image as the primary path and a named volume for persistent SQLite storage.

**Tech Stack:** Python 3.11, FastAPI lifespan, pytest/pytest-asyncio, Docker Compose, Markdown.

## Global Constraints

- Do not read or expose real `.env`, SQLite, log, server, username, password, token, or deployment values.
- Preserve the existing now-playing response fields and `seconds_elapsed` wall-clock semantics.
- Do not change playback counting, SQLite schema, authentication, or dashboard layout.
- `README.md` contains English prose; `README.zh-CN.md` contains Chinese prose.
- Use `stepaniah/navidrome-statistic` as the primary published image and port `39421`.
- Do not create a Git commit unless the user explicitly requests one.

---

### Task 1: Reproduce Multi-Server Live-State Regression

**Files:**
- Modify: `tests/test_main.py`
- Modify: `tests/test_lifespan.py`
- Modify: `tests/test_metrics.py`

**Interfaces:**
- Consumes: `PlaybackSessionTracker.active_sessions`, `api_now_playing()`, `build_readiness_report()`, `api_metrics()`.
- Produces: failing expectations for registered tracker aggregation and paused-session exclusion.

- [ ] **Step 1: Add synthetic tracker aggregation tests**

Create two trackers with no-op async save callbacks, populate active sessions using fixed synthetic values, register both through the runtime registry interface expected from Task 2, and assert `/api/stats/now-playing` returns both active entries but excludes an entry with `paused=True`.

- [ ] **Step 2: Add observability consistency tests**

Assert readiness JSON reports the number of non-paused sessions across registered trackers and Prometheus output contains `navidrome_stat_active_sessions 2` for the same state.

- [ ] **Step 3: Add lifecycle cleanup test**

Patch server configuration and polling so lifespan creates a per-server tracker, assert it is present while lifespan is active, and assert the runtime registry is empty after shutdown.

- [ ] **Step 4: Run the focused tests and verify the regression**

Run: `python -m pytest -q tests/test_main.py tests/test_lifespan.py tests/test_metrics.py`

Expected: new tests fail because no runtime tracker registry exists and current readers only inspect `session_tracker`.

### Task 2: Implement the Runtime Tracker Registry

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main.py`
- Test: `tests/test_lifespan.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Produces: `_runtime_trackers: list[PlaybackSessionTracker]`, `_live_trackers() -> tuple[PlaybackSessionTracker, ...]`, `_active_sessions() -> list[dict]`.
- `_live_trackers()` returns registered lifespan trackers when present; otherwise it returns `(session_tracker,)`.
- `_active_sessions()` returns only sessions where `session.get("paused")` is false.

- [ ] **Step 1: Add the minimal registry helpers**

Define the runtime list after `session_tracker`. Snapshot tracker and session values into tuples/lists before iteration so endpoint reads do not depend on mutation during iteration.

- [ ] **Step 2: Register and unregister lifespan trackers**

Append a tracker only after client construction succeeds and before its task starts. In shutdown, finalize trackers and remove each from the registry in a `finally`-style cleanup path so no stale tracker remains after normal shutdown.

- [ ] **Step 3: Switch every live-session reader**

Use `_active_sessions()` in `/api/stats/now-playing`, readiness `metrics.active_sessions`, and `/metrics`. Keep `polling_loop(client)` bound to the global tracker for existing direct tests.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest -q tests/test_main.py tests/test_lifespan.py tests/test_metrics.py`

Expected: all focused tests pass.

### Task 3: Rewrite Operator Documentation

**Files:**
- Modify: `README.md`
- Create: `README.zh-CN.md`

**Interfaces:**
- Produces: canonical English operator guide and linked Chinese translation.

- [ ] **Step 1: Rewrite the English README**

Use sections for overview, limitations, features, published-image Docker deployment, configuration, operation, security/privacy, source build, development, project docs, and license. Remove mixed Chinese prose and the promotional AI-generation statement.

- [ ] **Step 2: Add the published-image Compose example**

Use `image: stepaniah/navidrome-statistic:latest`, `user: "1000:1000"`, port `39421:39421`, named volume `navidrome-stat-data:/data`, synthetic `.env` values, restart policy, and `/health` health check. Explain version pinning, updates, backup/restore while stopped, and source-build alternative.

- [ ] **Step 3: Create the Chinese translation**

Mirror the English facts and order in Chinese, link back to `README.md`, retain only required technical identifiers in English, and avoid duplicating release-maintainer instructions in the deployment flow.

- [ ] **Step 4: Check language and privacy constraints**

Search the English file for Chinese characters and inspect any matches; search both files for credential-looking assignments and ensure every value is a reserved-domain example or explicit placeholder.

### Task 4: Synchronize Project Facts and Complete Verification

**Files:**
- Modify: `docs/current-state.md`
- Modify: `docs/interfaces.md`
- Modify: `docs/privacy.md`
- Modify: `docs/tasks.md`
- Verify: `docs/superpowers/specs/2026-07-27-readme-now-playing-design.md`
- Verify: `docs/superpowers/plans/2026-07-27-readme-now-playing.md`

**Interfaces:**
- Consumes: final runtime behavior and README deployment instructions.
- Produces: accurate interface/privacy facts and NDS-DOC-002 completion evidence.

- [ ] **Step 1: Update current-state and interface facts**

Document per-server runtime aggregation, paused-session exclusion, unchanged response fields, and shared readiness/metrics counts. Correct stale statements that claim only the old global tracker is read.

- [ ] **Step 2: Update privacy guidance**

Record that the named Docker volume contains plaintext listening metadata and credentials saved through the UI, and that backups inherit those sensitivities. Do not add deployment-specific values.

- [ ] **Step 3: Run complete verification**

Run:

```bash
python -m pytest -q
python3 scripts/check_md_links.py
docker compose config
git diff --check
git diff --stat
git diff
git status --short --branch
```

Expected: tests and checks pass; Compose renders without secrets; only intended files are changed.

- [ ] **Step 4: Attempt the Docker smoke test when available**

Run `docker info`. If available, run `bash scripts/docker_smoke_test.sh`; otherwise record the Docker daemon as an environment blocker without claiming a smoke-test pass.

- [ ] **Step 5: Complete NDS-DOC-002**

Set status to `已完成` only after every acceptance criterion passes. Record the date, implementation summary, exact verification results, no commit/PR, Docker smoke result or blocker, and residual risks.
