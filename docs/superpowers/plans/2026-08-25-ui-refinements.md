# UI Refinements (v0.8.x) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the eight v0.8.x UI refinements from `docs/superpowers/specs/2026-08-25-ui-refinements-design.md`: header branding with live version, `/api/about`-sourced version everywhere, custom year selector, review chart layout, review cover art, inline connection-test status, recent-plays server label relocation with column visibility, and corrected brand icon geometry.

**Architecture:** Vanilla ES modules served by FastAPI, unchanged. Two new shared modules (`js/app-info.js`, `js/listbox.js`) join the existing `js/` helpers. Backend changes are limited to the review aggregation payload (`source_id` per item) and default version constants.

**Tech Stack:** Python 3 / FastAPI, vanilla JS ES modules, ECharts, pytest (static-source assertions pattern), `node --test`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-25-ui-refinements-design.md` — requirements there are verbatim authoritative.
- No version strings hardcoded in any frontend file; the only source is `GET /api/about`.
- `messages-dashboard.js` and `messages-settings.js` keys must exist in all five locales (zhCN, zhTW, en, ja, de). `messages-review.js` keys in its four locales (zhCN, zhTW, en, ja) — the review page does not load German today.
- Frontend keeps the repo's DOM APIs: `createElement`/`textContent` only, no `innerHTML` with dynamic data.
- Python tests follow the static-source assertion pattern of `tests/test_static_*.py` for markup/JS checks.
- Run Python tests with `pytest`; node tests with `npm run test:unit`.
- Commit after every task, message style: `feat:/fix:/refactor: scope: summary` (match `git log`).

---

### Task 1: Version plumbing — `app-info.js`, About page row, default bumps

**Files:**
- Create: `src/static/js/app-info.js`
- Modify: `src/version.py:3`
- Modify: `Dockerfile` (ARG APP_VERSION line)
- Modify: `src/static/settings.html` (About panel `dl.about-list`, inline `<style>`)
- Modify: `src/static/settings.js` (imports, `bootstrapData`, login submit handler)
- Modify: `src/static/js/messages-settings.js` (five locale blocks, next to each `about.heading`)
- Test: `tests/test_static_settings.py`

**Interfaces:**
- Produces: `fetchAppInfo(): Promise<object|null>`, `applyAppVersion(): Promise<void>` from `js/app-info.js`. Later tasks (10) import `applyAppVersion`.
- Produces: `[data-app-version]` convention — any element with this attribute gets `v{version}` text.

- [ ] **Step 1: Write failing static tests**

Append to `tests/test_static_settings.py`:

```python
def test_about_panel_has_version_row_served_by_api():
    html = _read(SETTINGS_HTML)
    assert 'data-i18n="about.version"' in html
    assert "data-app-version" in html


def test_settings_runtime_fills_version_from_about_endpoint():
    js = _read(SETTINGS_JS)
    assert "applyAppVersion" in js
    assert '"/api/about"' not in js  # fetched via js/app-info.js, not inline
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_static_settings.py -q`
Expected: 2 failures (about.version missing, applyAppVersion missing).

- [ ] **Step 3: Create `src/static/js/app-info.js`**

```js
/**
 * Application metadata from `/api/about`.
 *
 * The backend serves the released version so frontend files never hardcode
 * one. Failed lookups stay silent and are retried on the next call.
 */

import { apiFetch } from './http.js';

let appInfoPromise = null;

function fetchAppInfo() {
    if (!appInfoPromise) {
        appInfoPromise = apiFetch('/api/about')
            .then((response) => {
                if (!response.ok) {
                    appInfoPromise = null;
                    return null;
                }
                return response.json();
            })
            .catch(() => {
                appInfoPromise = null;
                return null;
            });
    }
    return appInfoPromise;
}

async function applyAppVersion() {
    const info = await fetchAppInfo();
    if (!info || !info.version) return;
    document.querySelectorAll('[data-app-version]').forEach((element) => {
        element.textContent = `v${info.version}`;
    });
}

export { fetchAppInfo, applyAppVersion };
```

- [ ] **Step 4: Bump stale defaults**

`src/version.py` line 3:

```python
APP_VERSION = os.getenv("APP_VERSION", "0.8.0-dev")
```

`Dockerfile`: change `ARG APP_VERSION=0.7.0-dev` to `ARG APP_VERSION=0.8.0-dev` (both stages if repeated).

- [ ] **Step 5: About panel row in `settings.html`**

Inside `<dl class="about-list">`, insert as the first row (above the Project row):

```html
<div class="about-row">
    <dt data-i18n="about.version">Version</dt>
    <dd><span data-app-version></span></dd>
</div>
```

- [ ] **Step 6: i18n keys in `messages-settings.js`**

Add next to each locale's `about.heading` entry:

- zhCN: `['about.version', '版本'],`
- zhTW: `['about.version', '版本'],`
- en: `['about.version', 'Version'],`
- ja: `['about.version', 'バージョン'],`
- de: `['about.version', 'Version'],`

- [ ] **Step 7: Wire into `settings.js`**

Add import with the other `js/` imports:

```js
import { applyAppVersion } from './js/app-info.js';
```

In `bootstrapData()` (around line 1148), add `applyAppVersion();` as the first statement after `hideBanner();`. In `bindAuthentication()`'s submit handler, add `applyAppVersion();` immediately after the `await submitLogin(tokenInput.value);` line so the badge fills once a session exists.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_static_settings.py tests/test_about.py -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/static/js/app-info.js src/version.py Dockerfile src/static/settings.html src/static/settings.js src/static/js/messages-settings.js tests/test_static_settings.py
git commit -m "feat(ui): serve app version from /api/about into About panel"
```

---

### Task 2: Shared `listbox.js` module

**Files:**
- Create: `src/static/js/listbox.js`

**Interfaces:**
- Produces: `createListbox({ trigger, menu, onSelect })` → `{ setOpen(next, { restoreFocus }), setSelected(value), open }`. Options are `<button role="option" data-value="...">` children of `menu`; selection state via `aria-selected`.
- Produces: `attachPopover({ trigger, panel })` → `{ setOpen(next, { restoreFocus }), open }` for non-listbox panels (used by Task 9's column menu).
- Consumers: Task 3 (year selector), Task 9 (column menu). The dashboard's existing filter menus stay on their local implementation.

- [ ] **Step 1: Create the module**

```js
/**
 * Popover listbox controls shared across pages.
 *
 * Interaction mirrors the dashboard filter menus: toggle on click, close on
 * outside click or Escape, arrow-key navigation, focus restore on close.
 */

function focusOption(menu, option) {
    const options = [...menu.querySelectorAll('[role="option"]')]
        .filter((item) => item instanceof HTMLButtonElement);
    options.forEach((item) => { item.tabIndex = item === option ? 0 : -1; });
    if (option) option.focus();
}

function createListbox({ trigger, menu, onSelect }) {
    let open = false;

    function setOpen(next, { restoreFocus = false } = {}) {
        open = next;
        trigger.setAttribute('aria-expanded', next ? 'true' : 'false');
        menu.classList.toggle('hidden', !next);
        if (next) {
            const selected = menu.querySelector('[role="option"][aria-selected="true"]');
            focusOption(menu, selected || menu.querySelector('[role="option"]'));
        } else if (restoreFocus) {
            trigger.focus();
        }
    }

    trigger.addEventListener('click', () => setOpen(!open));
    trigger.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            if (!open) setOpen(true);
        }
    });
    menu.addEventListener('keydown', (event) => {
        const options = [...menu.querySelectorAll('[role="option"]')]
            .filter((item) => item instanceof HTMLButtonElement);
        if (!options.length) return;
        const currentIndex = Math.max(0, options.indexOf(document.activeElement));
        let nextIndex = null;
        if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % options.length;
        else if (event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + options.length) % options.length;
        else if (event.key === 'Home') nextIndex = 0;
        else if (event.key === 'End') nextIndex = options.length - 1;
        else if (event.key === 'Escape') {
            event.preventDefault();
            setOpen(false, { restoreFocus: true });
            return;
        }
        if (nextIndex !== null) {
            event.preventDefault();
            focusOption(menu, options[nextIndex]);
        }
    });
    menu.addEventListener('click', (event) => {
        const option = event.target.closest('[role="option"]');
        if (!option) return;
        menu.querySelectorAll('[role="option"]').forEach((item) => {
            item.setAttribute('aria-selected', item === option ? 'true' : 'false');
        });
        setOpen(false, { restoreFocus: true });
        if (onSelect) onSelect(option);
    });
    document.addEventListener('click', (event) => {
        if (!open) return;
        if (trigger.contains(event.target) || menu.contains(event.target)) return;
        setOpen(false);
    });

    return {
        setOpen,
        get open() { return open; },
        setSelected(value) {
            menu.querySelectorAll('[role="option"]').forEach((item) => {
                item.setAttribute('aria-selected', item.dataset.value === value ? 'true' : 'false');
            });
        },
    };
}

function attachPopover({ trigger, panel }) {
    let open = false;

    function setOpen(next, { restoreFocus = false } = {}) {
        open = next;
        trigger.setAttribute('aria-expanded', next ? 'true' : 'false');
        panel.classList.toggle('hidden', !next);
        if (next) {
            const focusable = panel.querySelector('button, input');
            if (focusable) focusable.focus();
        } else if (restoreFocus) {
            trigger.focus();
        }
    }

    trigger.addEventListener('click', () => setOpen(!open));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && open) setOpen(false, { restoreFocus: true });
    });
    document.addEventListener('click', (event) => {
        if (!open) return;
        if (trigger.contains(event.target) || panel.contains(event.target)) return;
        setOpen(false);
    });

    return { setOpen, get open() { return open; } };
}

export { createListbox, attachPopover };
```

- [ ] **Step 2: Verify import graph stays clean**

Run: `node --input-type=module -e "import('./src/static/js/listbox.js').then(m => console.log(typeof m.createListbox, typeof m.attachPopover))"`
Expected: `function function` (module has no DOM side effects at import time).

- [ ] **Step 3: Commit**

```bash
git add src/static/js/listbox.js
git commit -m "feat(ui): shared popover listbox module"
```

---

### Task 3: Year in Review custom year selector

**Files:**
- Modify: `src/static/review.html:26-31`
- Modify: `src/static/js/review.js` (imports, `fillYearSelect`, `bootstrap`)
- Modify: `src/static/dashboard.css:807-814` (remove dead `.review-year-select`)
- Modify: `src/static/js/messages-review.js` (add `review.yearSelector` in its four locales)

**Interfaces:**
- Consumes: `createListbox` from Task 2.

- [ ] **Step 1: Write failing static test**

Create `tests/test_static_review.py`:

```python
"""Source-level checks for the Year in Review page."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW_HTML = ROOT / "src" / "static" / "review.html"
REVIEW_JS = ROOT / "src" / "static" / "js" / "review.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_year_selector_uses_custom_listbox_not_native_select():
    assert "<select" not in _read(REVIEW_HTML)
    assert 'id="reviewYearMenu"' in _read(REVIEW_HTML)
    assert "createListbox" in _read(REVIEW_JS)
```

Run: `pytest tests/test_static_review.py -q`
Expected: FAIL (`<select` present, no `reviewYearMenu`).

- [ ] **Step 2: Replace the select in `review.html`**

Swap the `.dashboard-filters` block for:

```html
<div class="dashboard-filters">
    <div class="filter-control window" id="reviewYearControl">
        <button id="reviewYearButton" type="button" class="filter-trigger" aria-haspopup="listbox" aria-expanded="false" aria-controls="reviewYearMenu">
            <svg class="filter-trigger-icon window" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M8 7V3m8 4V3M5 11h14M5 5h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z"/></svg>
            <span class="filter-trigger-copy">
                <span class="visually-hidden" data-i18n="review.year">Year</span>
                <span id="reviewYearButtonLabel" class="filter-trigger-value">2026</span>
            </span>
            <svg class="filter-trigger-chevron" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
        </button>
        <div id="reviewYearMenu" class="filter-popover hidden" role="listbox" aria-label="Year" data-i18n-attr="aria-label:review.year"></div>
    </div>
</div>
```

- [ ] **Step 3: Rewrite `fillYearSelect` in `review.js`**

Add import:

```js
import { createListbox } from './listbox.js';
```

Replace the whole `fillYearSelect` function with:

```js
let yearListbox = null;

function fillYearSelect() {
    const menu = document.getElementById('reviewYearMenu');
    const label = document.getElementById('reviewYearButtonLabel');
    const current = new Date().getFullYear();
    const fragment = document.createDocumentFragment();
    for (let year = current; year >= current - 5; year -= 1) {
        const option = document.createElement('button');
        option.type = 'button';
        option.setAttribute('role', 'option');
        option.className = 'filter-option review-year-option';
        option.dataset.value = String(year);
        const text = document.createElement('span');
        text.textContent = String(year);
        const check = document.createElement('span');
        check.className = 'option-check';
        check.setAttribute('aria-hidden', 'true');
        check.textContent = '✓';
        option.append(text, check);
        fragment.appendChild(option);
    }
    menu.replaceChildren(fragment);
    label.textContent = String(currentYear);
    yearListbox = createListbox({
        trigger: document.getElementById('reviewYearButton'),
        menu,
        onSelect: (option) => {
            const year = Number(option.dataset.value);
            if (!Number.isFinite(year) || year === currentYear) return;
            currentYear = year;
            label.textContent = String(currentYear);
            loadReview();
        },
    });
    yearListbox.setSelected(String(currentYear));
}
```

In `bootstrap()`, delete the old `document.getElementById('reviewYear').addEventListener('change', ...)` block (the selector no longer exists).

- [ ] **Step 4: i18n key**

`messages-review.js`, next to each locale's `review.year` entry, add:

- zhCN: `['review.yearSelector', '选择年份'],`
- zhTW: `['review.yearSelector', '選擇年份'],`
- en: `['review.yearSelector', 'Select year'],`
- ja: `['review.yearSelector', '年を選択'],`

Use it for the trigger's visually-hidden label: change `data-i18n="review.year"` on the hidden span to `data-i18n="review.yearSelector"`, keeping `data-i18n-attr="aria-label:review.year"` on the menu.

- [ ] **Step 5: Remove dead CSS**

Delete the `.review-year-select` rule block from `dashboard.css` (lines ~807-814).

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_static_review.py -q && npm run test:unit`
Expected: pass, including i18n parity.

- [ ] **Step 7: Commit**

```bash
git add src/static/review.html src/static/js/review.js src/static/dashboard.css src/static/js/messages-review.js tests/test_static_review.py
git commit -m "feat(review): custom year selector matching dashboard filters"
```

---

### Task 4: Year in Review chart layout

**Files:**
- Modify: `src/static/js/review.js:50-94` (`barOption`, `renderCharts`)
- Modify: `src/static/dashboard.css:861-862` (chart heights)
- Test: `tests/test_static_review.py`

**Interfaces:**
- Consumes: nothing new. `barOption(categories, values, { horizontal, categoryInterval })` signature changes — both call sites updated in the same task.

- [ ] **Step 1: Write failing test**

Append to `tests/test_static_review.py`:

```python
def test_review_charts_prevent_axis_label_overlap():
    js = _read(REVIEW_JS)
    assert "hideOverlap: true" in js
    assert "categoryInterval" in js
    assert "containLabel: true" in js

def test_review_chart_heights_increased():
    css = _read(ROOT / "src" / "static" / "dashboard.css")
    assert ".review-chart { width: 100%; height: 260px; }" in css
    assert ".review-chart-tall { height: 300px; }" in css
```

Run: `pytest tests/test_static_review.py -q`
Expected: new tests FAIL.

- [ ] **Step 2: Rewrite `barOption` and `renderCharts`**

Replace both functions in `review.js`:

```js
function barOption(categories, values, { horizontal = false, categoryInterval = 0 } = {}) {
    const categoryAxis = {
        type: 'category',
        data: categories,
        axisLine: { lineStyle: { color: 'rgba(128,128,140,0.25)' } },
        axisLabel: {
            color: chartBase().textStyle.color,
            fontSize: 11,
            hideOverlap: true,
            interval: categoryInterval,
        },
        axisTick: { show: false },
    };
    const valueAxis = {
        type: 'value',
        axisLabel: { color: chartBase().textStyle.color, fontSize: 11, hideOverlap: true },
        splitLine: { lineStyle: { color: 'rgba(128,128,140,0.15)' } },
    };
    return {
        backgroundColor: 'transparent',
        textStyle: chartBase().textStyle,
        tooltip: { ...chartBase().tooltip, trigger: 'axis' },
        grid: { left: 8, right: 20, top: 16, bottom: 8, containLabel: true },
        ...(horizontal
            ? { xAxis: { ...valueAxis, splitNumber: 4 }, yAxis: categoryAxis }
            : { xAxis: categoryAxis, yAxis: valueAxis }),
        series: [{
            type: 'bar',
            data: values,
            itemStyle: { color: chartPalette[0], borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
            barMaxWidth: 26,
        }],
    };
}

function renderCharts(review) {
    monthlyChart.setOption(barOption(
        review.monthly.map((entry) => entry.month.slice(5)),
        review.monthly.map((entry) => entry.count),
    ));
    hourlyChart.setOption(barOption(
        review.hourly.map((entry) => String(entry.hour)),
        review.hourly.map((entry) => entry.count),
        { categoryInterval: 2 },
    ));
    weekdayChart.setOption(barOption(
        review.weekday.map((entry) => t(`weekday.${['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][entry.weekday]}`)),
        review.weekday.map((entry) => entry.count),
        { horizontal: true },
    ));
}
```

- [ ] **Step 3: Chart heights in `dashboard.css`**

```css
.review-chart { width: 100%; height: 260px; }
.review-chart-tall { height: 300px; }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_static_review.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/static/js/review.js src/static/dashboard.css tests/test_static_review.py
git commit -m "fix(review): chart axis labels and grid spacing no longer collide"
```

---

### Task 5: Review cover art — backend `source_id`

**Files:**
- Modify: `src/schemas.py:345-352` (`ReviewTopItem`)
- Modify: `src/stats_queries.py` (`get_review_summary` top_tracks block, ~line 749)
- Modify: `src/stats_service.py:192-205` (`review`)
- Test: `tests/test_review.py`

**Interfaces:**
- Produces: every `ReviewTopItem` may carry `source_id: str | None`. Tracks always carry their own source id; albums carry the effective source id (request filter, else the single configured server, else `None`).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_review.py`:

```python
@pytest.mark.asyncio
async def test_review_top_tracks_carry_source_id(seeded_db, isolated_db):
    year = seeded_db
    review = await get_review_summary(year, "UTC", db_path=isolated_db)
    tracks = {entry["name"]: entry for entry in review["top_tracks"]}
    assert tracks["Morning Song"]["source_id"] == "legacy"
    assert tracks["Morning Song"]["track_id"] == "t-1"
```

Add the needed imports near the top of the file (after existing imports):

```python
import src.stats_service as stats_service_module


class FakeCache:
    async def invalidate(self):
        pass

    async def get_or_create(self, _key, factory):
        return await factory()
```

The album stamping test monkeypatches `list_servers` inside `stats_service` (the review build resolves the effective source from it). With a single configured server the albums must carry its id:

```python
@pytest.mark.asyncio
async def test_review_albums_stamp_single_server_source(seeded_db, isolated_db, monkeypatch):
    year = seeded_db
    async def fake_list_servers():
        return [{"id": "srv-1", "display_name": "Main"}]
    monkeypatch.setattr(stats_service_module, "list_servers", fake_list_servers)
    service = stats_service_module.StatsService(cache=FakeCache(), retry_attempts=1)
    review = await service.review(year=year, timezone_name="UTC", source_id=None)
    assert review["top_albums"]
    for entry in review["top_albums"]:
        assert entry["source_id"] == "srv-1"
```

Run: `pytest tests/test_review.py -q`
Expected: new tests FAIL (`source_id` key missing / not stamped).

- [ ] **Step 2: Schema field**

`src/schemas.py` `ReviewTopItem` gains one line before `album_id`:

```python
    source_id: Optional[str] = None
```

- [ ] **Step 3: Track source ids in `stats_queries.py`**

In `get_review_summary`, replace the `top_tracks` comprehension:

```python
    top_tracks = [
        {
            "name": row["name"] or "-",
            "source_id": row["track_key"].split("\x1f", 1)[0],
            "track_id": row["track_key"].split("\x1f", 1)[1] if "\x1f" in row["track_key"] else row["track_key"],
            "count": int(row["count"] or 0),
            "total_listen_sec": int(row["value"] or 0),
            "value": int(row["value"] or 0),
        }
        for row in track_rows
    ]
```

- [ ] **Step 4: Stamp albums in `stats_service.review`**

Replace the `build()` body:

```python
        async def build() -> dict:
            summary = await get_review_summary(
                year, timezone_name, source_id=source_id
            )
            servers = await list_servers()
            effective_source = source_id
            if effective_source is None and len(servers) == 1:
                effective_source = servers[0].get("id")
            summary["top_albums"] = await self._attach_album_ids(
                source_id, summary["top_albums"], servers
            )
            for entry in summary["top_albums"]:
                entry["source_id"] = effective_source
            return summary
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_review.py tests/test_stats_service.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/schemas.py src/stats_queries.py src/stats_service.py tests/test_review.py
git commit -m "feat(review): include source ids for cover art resolution"
```

---

### Task 6: Review cover art — frontend

**Files:**
- Modify: `src/static/js/review.js:96-144` (`coverImage`, `renderTopList`)
- Modify: `src/static/dashboard.css:898` (`.review-top-cover` flex)

**Interfaces:**
- Consumes: `entry.source_id` from Task 5.

- [ ] **Step 1: Write failing test**

Append to `tests/test_static_review.py`:

```python
def test_review_covers_use_per_item_source_with_letter_fallback():
    js = _read(REVIEW_JS)
    assert "entry.source_id || sourceId" in js
    assert "review-top-cover-fallback" in js
```

Run: `pytest tests/test_static_review.py -q`
Expected: FAIL.

- [ ] **Step 2: Rewrite cover rendering in `review.js`**

Replace `coverImage` and the cover portion of `renderTopList`:

```js
function letterFallback(text) {
    const placeholder = document.createElement('span');
    placeholder.className = 'review-top-cover review-top-cover-fallback';
    placeholder.textContent = String(text || '?').charAt(0).toUpperCase();
    return placeholder;
}

function coverImage(sourceId, id, className, fallbackText) {
    if (!sourceId || !id) return letterFallback(fallbackText);
    const img = document.createElement('img');
    img.className = className;
    img.loading = 'lazy';
    img.decoding = 'async';
    img.alt = '';
    const params = new URLSearchParams({ source_id: sourceId, id, size: '300' });
    img.src = `/api/coverart?${params.toString()}`;
    img.addEventListener('error', () => img.replaceWith(letterFallback(fallbackText)));
    return img;
}
```

In `renderTopList`, replace the cover block with:

```js
        const id = coverId === 'album_id' ? entry.album_id : entry.track_id;
        li.appendChild(coverImage(entry.source_id || sourceId, id, 'review-top-cover', entry.name));
```

- [ ] **Step 3: CSS shrink guard**

`.review-top-cover` rule becomes:

```css
.review-top-cover { width: 38px; height: 38px; border-radius: 5px; object-fit: cover; flex: 0 0 auto; }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_static_review.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/static/js/review.js src/static/dashboard.css tests/test_static_review.py
git commit -m "fix(review): resolve top-list cover art per source with letter fallback"
```

---

### Task 7: Settings inline connection-test status

**Files:**
- Modify: `src/static/settings.js:597-677` (`renderServers`)
- Modify: `src/static/settings.html` (inline `<style>`, near `.server-status` ~line 973)
- Test: `tests/test_static_settings.py`

**Interfaces:**
- Consumes: existing messages `source.testing`, `source.testSuccess`, `source.testFailure`, `source.testFailed`; CSS vars `--success`, `--danger` already defined per theme in `settings.html`.

- [ ] **Step 1: Write failing test**

Append to `tests/test_static_settings.py`:

```python
def test_server_row_test_result_renders_inline_not_in_form():
    js = _read(SETTINGS_JS)
    assert "server-test-status" in js
    html = _read(SETTINGS_HTML)
    assert ".server-test-status" in html
```

Run: `pytest tests/test_static_settings.py -q`
Expected: FAIL.

- [ ] **Step 2: Per-row status in `renderServers`**

In `settings.js` `renderServers`, create the status element with the identity block and rewire the test button:

```js
            const testStatus = document.createElement('span');
            testStatus.className = 'server-test-status';
            testStatus.hidden = true;
            identity.append(name, detailLine, testStatus);
```

Replace the `testButton` click handler:

```js
            testButton.addEventListener('click', async () => {
                testStatus.hidden = false;
                testStatus.dataset.kind = 'info';
                testStatus.textContent = t('source.testing');
                try {
                    const testResponse = await apiFetch(`/api/servers/${encodeURIComponent(server.id)}/test`, {
                        method: 'POST',
                    });
                    if (!isResponseOk(testResponse)) throw new Error('server test failed');
                    const result = await testResponse.json();
                    testStatus.dataset.kind = result.ok ? 'success' : 'error';
                    testStatus.textContent = t(result.ok ? 'source.testSuccess' : 'source.testFailure');
                } catch (error) {
                    if (error.message !== 'unauthorized') {
                        testStatus.dataset.kind = 'error';
                        testStatus.textContent = t('source.testFailed');
                    }
                }
            });
```

The form's `测试当前表单` handler keeps calling `setSourceMessage` unchanged.

- [ ] **Step 3: CSS in `settings.html` style block**

Insert after the `.server-status[data-enabled="false"]` rule:

```css
        .server-test-status { display: block; margin-top: 6px; font-size: 0.75rem; color: var(--text-muted); }
        .server-test-status[data-kind="success"] { color: var(--success); }
        .server-test-status[data-kind="error"] { color: var(--danger); }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_static_settings.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/static/settings.js src/static/settings.html tests/test_static_settings.py
git commit -m "fix(settings): server connection test results render in their row"
```

---

### Task 8: Recent plays — server label into user column

**Files:**
- Modify: `src/static/dashboard.js` (`renderHistoryTable` ~line 1216, new `createSourceLabel` near `createSourceBadge` ~line 460)
- Modify: `src/static/dashboard.css` (history user cell rules, near `.history-cell-*` ~line 620)

**Interfaces:**
- Produces: `createSourceLabel(item)` → `<span class="history-user-source">` or `null`. `createSourceBadge` remains for the now-playing list.

- [ ] **Step 1: Write failing test**

Append to `tests/test_static_dashboard.py` (the file already defines a module-scoped `source` fixture over the dashboard sources):

```python
def test_history_server_label_lives_in_user_column(source):
    assert "history-user-source" in source
    assert "history-user-meta" in source
```

Run: `pytest tests/test_static_dashboard.py -q`
Expected: FAIL.

- [ ] **Step 2: Add `createSourceLabel` in `dashboard.js`**

Directly after `createSourceBadge`:

```js
    function createSourceLabel(item) {
        const sourceName = item && (item.source_name || item.source_id);
        if (!sourceName) return null;
        const label = document.createElement('span');
        label.className = 'history-user-source';
        label.textContent = String(sourceName);
        label.title = dashboardMessage('label.source', { name: sourceName });
        return label;
    }
```

- [ ] **Step 3: Rewire `renderHistoryTable`**

Replace the user cell construction:

```js
            const userTd = document.createElement('td');
            userTd.className = 'history-cell history-cell-user';
            const userSpan = document.createElement('span');
            userSpan.className = 'history-user-wrap';
            const avatar = document.createElement('span');
            avatar.className = 'history-avatar';
            avatar.textContent = String(item.username || '?').charAt(0).toUpperCase();
            avatar.setAttribute('aria-hidden', 'true');
            const userMeta = document.createElement('div');
            userMeta.className = 'history-user-meta';
            const userLabel = document.createElement('span');
            userLabel.className = 'history-user-label';
            userLabel.textContent = item.username || '-';
            userMeta.appendChild(userLabel);
            if (showSources) {
                const sourceLabel = createSourceLabel(item);
                if (sourceLabel) userMeta.appendChild(sourceLabel);
            }
            userSpan.appendChild(avatar);
            userSpan.appendChild(userMeta);
            userTd.appendChild(userSpan);
```

Delete the `if (showSources) { ... createSourceBadge ... }` block from the title cell construction.

- [ ] **Step 4: CSS**

In `dashboard.css`, near the existing history rules, add:

```css
        .history-user-wrap { display: flex; align-items: center; gap: 0.5rem; min-width: 0; }
        .history-user-meta { display: flex; flex-direction: column; min-width: 0; }
        .history-user-source {
            color: var(--app-dim);
            font-size: 0.7rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 9rem;
        }
```

If `.history-user-wrap` / `.history-user-label` rules already exist, merge rather than duplicate.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_static_dashboard.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/static/dashboard.js src/static/dashboard.css tests/test_static_dashboard.py
git commit -m "fix(dashboard): recent-plays server label moves under the username"
```

---

### Task 9: Recent plays — column visibility

**Files:**
- Modify: `src/static/index.html:344-372` (history section header + table)
- Modify: `src/static/dashboard.js` (imports, column constants, `setupHistoryColumns`, `applyHistoryColumns`, bootstrap wiring)
- Modify: `src/static/dashboard.css` (`.column-hidden`, `.columns-menu`)
- Modify: `src/static/js/messages-dashboard.js` (`history.columns` ×5 locales)
- Test: `tests/test_static_dashboard.py`

**Interfaces:**
- Consumes: `attachPopover` from Task 2; `readPreference`/`writePreference`/`onPreferenceChange` from `js/prefs.js`.
- Produces: localStorage key `navidrome-history-columns` holding a comma-separated subset of `user,track,artist,album,played,count`.

- [ ] **Step 1: Write failing test**

Append to `tests/test_static_dashboard.py`:

```python
def test_history_column_visibility_persisted_with_min_one_rule(source):
    assert "navidrome-history-columns" in source
    assert "columns.size === 1" in source
    assert "column-hidden" in source


def test_history_column_menu_messages_exist_in_all_locales(catalog_source):
    assert catalog_source.count("['history.columns'") == 5
```

Run: `pytest tests/test_static_dashboard.py -q`
Expected: FAIL.

- [ ] **Step 2: Header markup in `index.html`**

Replace the history section header block:

```html
            <div class="px-5 sm:px-6 py-5 border-b border-white/5">
                <div class="flex items-center justify-between gap-3">
                    <h2 class="text-sm font-semibold text-slate-300" data-i18n="dashboard.history">最近播放</h2>
                    <div class="filter-control columns" id="historyColumnsControl">
                        <button id="historyColumnsButton" type="button" class="header-icon-button" aria-haspopup="true" aria-expanded="false" aria-controls="historyColumnsPanel" data-i18n-attr="aria-label:history.columns,title:history.columns" aria-label="列设置" title="列设置">
                            <svg aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M3 6h18M3 12h18M3 18h18"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M9 3v18"/></svg>
                        </button>
                        <div id="historyColumnsPanel" class="filter-popover hidden" role="group" aria-label="列设置" data-i18n-attr="aria-label:history.columns"></div>
                    </div>
                </div>
                <p class="text-xs text-slate-600 mt-0.5" data-i18n="subtitle.history">按最近播放时间排序，重复收听会累加 Plays</p>
            </div>
```

Also add the matching cell classes to the table headers (they currently carry none, so `applyHistoryColumns` can target them):

```html
                    <thead>
                        <tr class="text-left text-xs font-medium text-slate-500 uppercase tracking-wider bg-ink-800/50">
                            <th scope="col" class="history-cell-user" data-i18n="history.user">用户</th>
                            <th scope="col" class="history-cell-title" data-i18n="history.track">曲目</th>
                            <th scope="col" class="history-cell-artist" data-i18n="history.artist">艺人</th>
                            <th scope="col" class="history-cell-album" data-i18n="history.album">专辑</th>
                            <th scope="col" class="history-cell-played" data-i18n="history.lastPlayed">最近播放</th>
                            <th scope="col" class="history-cell-count text-right" data-i18n="history.plays">播放次数</th>
                        </tr>
                    </thead>
```

- [ ] **Step 3: Column logic in `dashboard.js`**

Extend the prefs import:

```js
import { onPreferenceChange, readPreference, writePreference } from './js/prefs.js';
```

Add (module scope, near the other constants):

```js
import { attachPopover } from './js/listbox.js';

const HISTORY_COLUMNS_KEY = 'navidrome-history-columns';
const HISTORY_COLUMNS = [
    { id: 'user', label: 'history.user', cell: 'history-cell-user', col: 'history-col-user' },
    { id: 'track', label: 'history.track', cell: 'history-cell-title', col: 'history-col-track' },
    { id: 'artist', label: 'history.artist', cell: 'history-cell-artist', col: 'history-col-artist' },
    { id: 'album', label: 'history.album', cell: 'history-cell-album', col: 'history-col-album' },
    { id: 'played', label: 'history.lastPlayed', cell: 'history-cell-played', col: 'history-col-played' },
    { id: 'count', label: 'history.plays', cell: 'history-cell-count', col: 'history-col-count' },
];

function allHistoryColumns() {
    return new Set(HISTORY_COLUMNS.map((column) => column.id));
}

function readHistoryColumns() {
    const raw = readPreference(HISTORY_COLUMNS_KEY, '');
    if (!raw) return allHistoryColumns();
    const saved = new Set(raw.split(',')
        .filter((id) => HISTORY_COLUMNS.some((column) => column.id === id)));
    return saved.size ? saved : allHistoryColumns();
}

function applyHistoryColumns(columns) {
    for (const column of HISTORY_COLUMNS) {
        const visible = columns.has(column.id);
        document.querySelectorAll(`.history-table .${column.cell}, .history-table col.${column.col}`)
            .forEach((element) => element.classList.toggle('column-hidden', !visible));
    }
}

function setupHistoryColumns() {
    const button = document.getElementById('historyColumnsButton');
    const panel = document.getElementById('historyColumnsPanel');
    attachPopover({ trigger: button, panel });
    let columns = readHistoryColumns();

    function renderPanel() {
        const list = document.createElement('div');
        list.className = 'columns-menu';
        for (const column of HISTORY_COLUMNS) {
            const option = document.createElement('button');
            option.type = 'button';
            option.className = 'filter-option column-option';
            const text = document.createElement('span');
            text.textContent = dashboardMessage(column.label);
            const check = document.createElement('span');
            check.className = 'option-check';
            check.setAttribute('aria-hidden', 'true');
            check.textContent = '✓';
            option.append(text, check);
            option.setAttribute('aria-pressed', columns.has(column.id) ? 'true' : 'false');
            option.classList.toggle('column-option-off', !columns.has(column.id));
            option.disabled = columns.has(column.id) && columns.size === 1;
            option.addEventListener('click', () => {
                if (columns.has(column.id)) columns.delete(column.id);
                else columns.add(column.id);
                writePreference(HISTORY_COLUMNS_KEY, [...columns].join(','));
                columns = readHistoryColumns();
                renderPanel();
                applyHistoryColumns(columns);
            });
            list.appendChild(option);
        }
        panel.replaceChildren(list);
    }

    renderPanel();
    applyHistoryColumns(columns);
    onPreferenceChange(HISTORY_COLUMNS_KEY, () => {
        columns = readHistoryColumns();
        renderPanel();
        applyHistoryColumns(columns);
    });
}
```

Call `setupHistoryColumns();` in the bootstrap section next to `setActiveStatsWindowButton(statsDays);`.

- [ ] **Step 4: i18n keys**

`messages-dashboard.js`, next to each locale's `history.plays` entry, add `['history.columns', ...]`:

- zhCN: `'列设置'`
- zhTW: `'欄目設定'`
- en: `'Columns'`
- ja: `'表示項目'`
- de: `'Spalten'`

- [ ] **Step 5: CSS**

```css
        .columns-menu { display: flex; flex-direction: column; min-width: 10rem; }
        .column-option-off .option-check { visibility: hidden; }
        @media (min-width: 481px) {
            .history-table .column-hidden { display: none; }
            .history-table col.column-hidden { visibility: collapse; }
        }
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_static_dashboard.py -q && npm run test:unit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/static/index.html src/static/dashboard.js src/static/dashboard.css src/static/js/messages-dashboard.js tests/test_static_dashboard.py
git commit -m "feat(dashboard): configurable column visibility for recent plays"
```

---

### Task 10: Dashboard header brand + version badge

**Files:**
- Modify: `src/static/index.html:52` (title), footer unchanged
- Modify: `src/static/dashboard.css` (`.brand-version`, `.dashboard-brand` gap if needed)
- Modify: `src/static/js/dashboard.js` (import + `applyAppVersion` calls in `bootstrap` and `submitLogin`)
- Modify: `src/static/js/messages-dashboard.js` (remove `dashboard.title` ×5)
- Test: `tests/test_static_dashboard.py`

**Interfaces:**
- Consumes: `applyAppVersion` from Task 1.

- [ ] **Step 1: Write failing test**

Append to `tests/test_static_dashboard.py`:

```python
def test_header_shows_brand_name_and_live_version(source):
    assert ">Navidrome Stat</h1>" in source
    assert "data-app-version" in source
    assert 'data-i18n="dashboard.title"' not in source


def test_no_hardcoded_versions_in_frontend():
    for path in (INDEX_HTML, DASHBOARD_JS):
        text = path.read_text(encoding="utf-8")
        assert "0.8." not in text, path
```

Run: `pytest tests/test_static_dashboard.py -q`
Expected: FAIL (title still bound to i18n).

- [ ] **Step 2: Markup**

Replace the `<h1>` line:

```html
                    <h1 class="dashboard-title">Navidrome Stat</h1>
                    <span class="brand-version" data-app-version></span>
```

Both elements stay inside `div.dashboard-brand`, after the brand mark div.

- [ ] **Step 3: CSS**

```css
        .brand-version {
            color: var(--app-dim);
            font-family: "SF Mono", ui-monospace, monospace;
            font-size: 0.7rem;
            margin-left: 2px;
            white-space: nowrap;
        }
```

If `.dashboard-brand` is not already `display: flex; align-items: center; gap: 10px;`, make it so.

- [ ] **Step 4: Wire `applyAppVersion` in `dashboard.js`**

```js
import { applyAppVersion } from './js/app-info.js';
```

In `bootstrap()` (line ~1712), add `applyAppVersion();` as the first statement inside the `try`. In `submitLogin()` (line ~150), add `applyAppVersion();` right after `hideLogin();`.

- [ ] **Step 5: Remove `dashboard.title` from all five locale blocks in `messages-dashboard.js`**

Delete the five lines `['dashboard.title', ...],`. No other file references the key after Step 2.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_static_dashboard.py tests/test_static_label_layout.py -q && npm run test:unit`
Expected: PASS (i18n parity holds because the key is removed from every locale).

- [ ] **Step 7: Commit**

```bash
git add src/static/index.html src/static/dashboard.css src/static/dashboard.js src/static/js/messages-dashboard.js tests/test_static_dashboard.py
git commit -m "feat(dashboard): brand title with backend-served version badge"
```

---

### Task 11: Brand icon geometry correction

**Files:**
- Modify: `src/static/index.html:20-50` (inline header SVG)
- Modify: `assets/icon.svg`
- Modify: `assets/icon-dark.svg`
- Modify: `src/static/favicon.svg`

**Interfaces:**
- Consumes: geometry table from the spec, section 8. Each file keeps its own palette; only geometry changes.

- [ ] **Step 1: Write failing test**

Create `tests/test_static_brand_icon.py`:

```python
"""Brand icon geometry must match the reference artwork spec."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON_FILES = [
    ROOT / "assets" / "icon.svg",
    ROOT / "assets" / "icon-dark.svg",
    ROOT / "src" / "static" / "favicon.svg",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_ellipse_note_head_anywhere():
    for path in ICON_FILES:
        assert "<ellipse" not in _read(path), path


def test_note_head_is_circle_at_specified_center():
    for path in ICON_FILES:
        assert '<circle cx="59" cy="71" r="8"' in _read(path), path


def test_sound_arcs_use_corrected_radii():
    for path in ICON_FILES:
        text = _read(path)
        for radius in ("13.5", "20", "26.5"):
            assert f"A {radius} {radius} 0 0 0" in text, path


def test_header_svg_matches_shared_geometry():
    html = _read(ROOT / "src" / "static" / "index.html")
    assert '<circle cx="59" cy="71" r="8"' in html
    assert "brandWave" in html
    assert "<ellipse" not in html
```

Run: `pytest tests/test_static_brand_icon.py -q`
Expected: FAIL (ellipse present, old radii).

- [ ] **Step 2: Replace the header SVG in `index.html`**

Replace the entire contents of `div.dashboard-brand-mark` with:

```html
                    <div class="dashboard-brand-mark" aria-hidden="true">
                        <svg fill="none" viewBox="0 0 128 128">
                            <defs>
                                <linearGradient id="brandWave" gradientUnits="userSpaceOnUse" x1="50" y1="46" x2="38" y2="74">
                                    <stop offset="0" stop-color="#F97316"/>
                                    <stop offset="0.5" stop-color="#84CC16"/>
                                    <stop offset="1" stop-color="#22D3EE"/>
                                </linearGradient>
                                <linearGradient id="brandTrend" gradientUnits="userSpaceOnUse" x1="66" y1="90" x2="102" y2="56">
                                    <stop offset="0" stop-color="#F97316"/>
                                    <stop offset="0.5" stop-color="#A3E635"/>
                                    <stop offset="1" stop-color="#38BDF8"/>
                                </linearGradient>
                            </defs>
                            <path d="M 100.1 56.9 A 36.5 36.5 0 1 0 87.5 90" stroke="var(--app-text)" stroke-width="5" stroke-linecap="round"/>
                            <path d="M 50.69 60.36 A 13.5 13.5 0 0 0 45.55 72.18" stroke="url(#brandWave)" stroke-width="5" stroke-linecap="round"/>
                            <path d="M 46.69 55.24 A 20 20 0 0 0 39.08 72.74" stroke="url(#brandWave)" stroke-width="5" stroke-linecap="round"/>
                            <path d="M 42.68 50.12 A 26.5 26.5 0 0 0 32.60 73.31" stroke="url(#brandWave)" stroke-width="5" stroke-linecap="round"/>
                            <circle cx="59" cy="71" r="8" fill="var(--app-bg)" stroke="var(--app-text)" stroke-width="5"/>
                            <circle cx="59" cy="71" r="2.2" fill="var(--app-text)"/>
                            <path d="M 67 71 V 39.5" stroke="var(--app-text)" stroke-width="5" stroke-linecap="round"/>
                            <path d="M 67 39.5 L 82 45.5 V 56.5 L 67 50.5 Z" fill="var(--app-bg)" stroke="var(--app-text)" stroke-width="5" stroke-linejoin="round"/>
                            <path d="M 69 98.5 H 103" stroke="var(--app-text)" stroke-width="4.5" stroke-linecap="round"/>
                            <rect x="70.5" y="89.5" width="7" height="9" rx="1.5" fill="var(--app-bg)" stroke="var(--app-text)" stroke-width="4.5" stroke-linejoin="round"/>
                            <rect x="82" y="82" width="7" height="16.5" rx="1.5" fill="var(--app-bg)" stroke="var(--app-text)" stroke-width="4.5" stroke-linejoin="round"/>
                            <rect x="93.5" y="75.5" width="7" height="23" rx="1.5" fill="var(--app-bg)" stroke="var(--app-text)" stroke-width="4.5" stroke-linejoin="round"/>
                            <path d="M 70.5 86.5 L 81 77.5 L 96.5 66.5" stroke="url(#brandTrend)" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
                            <circle cx="70.5" cy="86.5" r="2.6" fill="var(--app-bg)" stroke="#F97316" stroke-width="3.5"/>
                            <circle cx="81" cy="77.5" r="2.6" fill="var(--app-bg)" stroke="#84CC16" stroke-width="3.5"/>
                            <circle cx="96.5" cy="66.5" r="4.5" fill="var(--app-bg)" stroke="#38BDF8" stroke-width="4"/>
                        </svg>
                    </div>
```

- [ ] **Step 3: Apply the same geometry to the three static files**

For each of `assets/icon.svg`, `assets/icon-dark.svg`, `src/static/favicon.svg`:

1. Keep the file's existing palette (stroke color, fill color, background rect). Read each file first and note its stroke/fill literals.
2. Rename the `signal` gradient to `wave` with `x1="50" y1="46" x2="38" y2="74"` and stops `#F97316` / `#84CC16` (0.5) / `#22D3EE`; keep the existing `trend` gradient definition unchanged.
3. Replace the geometry elements with the header SVG's paths/rects/circles from Step 2, substituting:
   - `var(--app-text)` → the file's stroke literal
   - `var(--app-bg)` → the file's fill literal
   - `url(#brandWave)` → `url(#wave)`

- [ ] **Step 4: Visual check**

Open `assets/icon.svg` and `src/static/favicon.svg` in a browser at 128 px and 512 px. Confirm: circular note head, three arcs concentric on the note head with no ring intersection, flag flush with stem, ring gap on the right side around the bar chart. Compare against the reference artwork in the spec discussion.

Run: `pytest tests/test_static_brand_icon.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/static/index.html assets/icon.svg assets/icon-dark.svg src/static/favicon.svg tests/test_static_brand_icon.py
git commit -m "fix(brand): icon geometry realigned with reference artwork"
```

---

### Task 12: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Python suite**

Run: `pytest -q`
Expected: all pass.

- [ ] **Step 2: Node suite**

Run: `npm run test:unit`
Expected: all pass (i18n parity includes new/removed keys).

- [ ] **Step 3: Rebuild vendored assets if Tailwind classes changed**

Run: `npm run build:assets`
Expected: build completes; `src/static/vendor/tailwind.css` regenerated.

- [ ] **Step 4: Manual pass**

Start the server and verify:

1. Dashboard header shows `Navidrome Stat` + `v…` badge from `/api/about`; About page shows the same version.
2. Review page: year selector opens the styled popover, keyboard works; monthly chart shows all 12 labels, hourly every 2 h, weekday value axis has no collisions.
3. Review top albums/tracks show real covers with a single server configured; letter fallback with multi-server no-filter.
4. Settings: per-row 测试 shows status in the row; form message untouched.
5. Recent plays: server name under username (all-servers view); column menu toggles persist across reload; last visible column cannot be disabled; mobile card layout unaffected.
6. Icon renders correctly in light and dark themes.

- [ ] **Step 5: Final commit (if build assets changed)**

```bash
git add -A
git commit -m "chore: rebuild vendored assets"
```
