# UI Refinements — v0.8.x

- **Status:** Approved
- **Date:** 2026-08-25
- **Scope:** Dashboard header branding, version metadata plumbing, Year in Review page (year selector, charts, top-list cover art), Settings connection-test feedback, Recent plays table (server label, column visibility), brand icon geometry.

## 1. Dashboard header branding

### Problem

The header title shows the localized generic label `播放统计` / `Playback Statistics` instead of the project name, and no released version is visible anywhere in the UI.

### Design

- The `h1.dashboard-title` renders the fixed brand name `Navidrome Stat`. The brand name is not localized; the `data-i18n="dashboard.title"` binding is removed and the `dashboard.title` message entries are dropped from all locales.
- A version badge is placed next to the title: `<span class="brand-version" data-app-version></span>`, styled as small muted monospaced text (`.brand-version` in `dashboard.css`), content served by the backend (section 2).
- The footer remains `Navidrome Stat` plus links. The version appears once, in the header.
- The Year in Review page keeps its `Year in Review` title and gains no version badge.

## 2. Version metadata single source

### Problem

`/api/about` already returns `name`, `version`, `schema_version`, `license` and `project_url`, but no frontend consumes it. The About panel lists no version. Stale fallback defaults (`0.7.0-dev`) remain in `src/version.py` and the `Dockerfile` `ARG`.

### Design

- New module `src/static/js/app-info.js`:
  - `fetchAppInfo()` calls `GET /api/about` once per page load and caches the parsed body in a module-level promise.
  - `applyAppVersion()` fills every `[data-app-version]` element with `v{version}`.
  - On failure the elements stay empty; no error UI.
- Consumers:
  - `dashboard.js` imports and invokes it during bootstrap (version badge in header).
  - `settings.js` fills the new About panel row (below).
- About panel (`settings.html` tab-about) gains a row at the top of `dl.about-list`:
  - `dt`: localized `about.version` (new message key in all five locales of `messages-settings.js`)
  - `dd`: `<span data-app-version></span>`
- Defaults refreshed to `0.8.0-dev` in `src/version.py` and the `Dockerfile` build arg. No version strings are hardcoded in frontend markup or scripts.

## 3. Year in Review: custom year selector

### Problem

The year picker is the only remaining native `<select>`; its popup renders with browser chrome and clashes with the design (screenshot feedback).

### Design

- New shared module `src/static/js/listbox.js` exporting:
  - `createListbox({ trigger, menu, options, selectedValue, onSelect, label })` for single-select menus.
  - `attachPopover({ trigger, panel })` for open/close/focus handling, reused by the column-visibility menu in section 7.
  - Trigger button carries `aria-haspopup="listbox"` / `aria-expanded`; menu is `role="listbox"` with `role="option"` buttons.
  - Behavior mirrors the dashboard filter menus: click toggles, outside click closes, `Escape` closes and restores focus, `ArrowUp/Down/Home/End` move option focus, selecting an option closes and restores focus.
  - Styling reuses `.filter-trigger` / `.filter-popover` / `.filter-option` classes from `dashboard.css`; check mark on the active option.
- `review.html`: the `<select id="reviewYear">` is replaced by the same `filter-control window` markup used on the dashboard (calendar icon + value label + chevron). `review.js` builds year options (current year back to current − 5) into the popover and wires `onSelect` to reload the review.
- The dashboard's own filter menus are not refactored onto the new module in this change; they already match the target look and behavior.

## 4. Year in Review: chart layout

### Problem

Axis labels overlap or vanish: the weekday chart's value axis renders `501020060`-style collisions, the monthly chart shows only two month labels, the hourly axis is crowded.

### Design

Changes confined to `barOption()` in `src/static/js/review.js`:

- Every axis label gets `hideOverlap: true`.
- Category axes:
  - Monthly: `interval: 0`, labels formatted as `01`…`12`.
  - Hourly: `interval: 2` (00, 02, … 22).
- Weekday chart (horizontal): value axis gets `splitNumber: 4` so tick labels have room; category axis (weekday names) keeps `interval: 0`.
- Grid becomes `{ left: 8, right: 20, top: 16, bottom: 8, containLabel: true }`, letting ECharts reserve label space on whichever side it needs.
- Chart heights: `.review-chart` 240 → 260 px, `.review-chart-tall` 280 → 300 px in `dashboard.css`.

## 5. Year in Review: top-list cover art

### Problem

Top albums/tracks render letter placeholders instead of cover art. `stats_service.review()` already resolves `album_id`, but the response carries no `source_id`, and `review.js` only derives a source from the `?source_id=` URL parameter, which is normally absent. Cover art resolution requires a source id.

### Design

Backend:

- `ReviewTopItem` (`src/schemas.py`) gains `source_id: Optional[str] = None`.
- `get_review_summary` (`src/stats_queries.py`):
  - `top_tracks`: the source id already embedded in `track_key` (`source || 'legacy'` prefix) is emitted per item as `source_id`.
  - `top_albums`: rows are aggregated by name across sources, so per-row source ids do not exist; `stats_service.review()` stamps the effective source (request filter, else the single configured server) onto `top_albums` entries alongside the existing `album_id` attachment.
  - When no effective source exists (multiple servers, no filter), `source_id` stays `null` and the frontend falls back to the letter placeholder.
- `tests/test_review.py` covers: track rows carry their own source id; album rows carry the effective source id; multi-server no-filter case leaves `source_id` null.

Frontend (`review.js`):

- `coverImage()` uses `entry.source_id || pageSourceId`.
- Cover `error` handler replaces the image with the letter placeholder instead of removing it, so a failed load degrades to the current fallback.
- CSS: `.review-top-cover { flex: 0 0 auto; }` so long names never compress the artwork; `.review-top-name` keeps its existing ellipsis.
- Top artists keep the letter placeholder: the schema stores no artist ids, so no artwork can be resolved. Adding artist id persistence is deferred to the roadmap.

## 6. Settings: inline connection test results

### Problem

The per-row `测试` button on a saved server writes into `#sourceMessage`, which lives inside the connection form below; the result appears in the wrong place.

### Design

- Each server row renders its own status line: `<span class="server-test-status" data-kind>` inserted after the actions row, showing `source.testing` / `source.testSuccess` / `source.testFailure` / `source.testFailed`.
- The status is scoped to the row: testing server A never mutates server B's line, and a new test clears the previous text first.
- The form's `测试当前表单` button keeps using `#sourceMessage`.
- New CSS `.server-test-status` with `[data-kind="success"|"error"|"info"]` colors in the `settings.html` inline style block (the settings page is self-contained and does not load `dashboard.css`).
- `tests/test_static_settings.py` asserts the row status element is used by the row test handler.

## 7. Recent plays table

### Problem

The server badge sits after the track title and dominates the row. Column selection is fixed.

### Design

Server label:

- `createSourceBadge` moves from the title cell to the user cell: the user cell becomes a two-line stack — username on top, server name underneath as `.history-user-source` (small, muted, ellipsized, `title` attribute for full name).
- Visibility rule unchanged: the server label renders only when no single source is filtered (`showSources`).

Column visibility:

- The section header gains a `列设置` icon button next to the title, opening a checkbox-style popover built on `attachPopover` from `js/listbox.js`, listing the six columns: 用户, 曲目, 艺人, 专辑, 最近播放, 播放次数.
- Toggling a column hides/shows the corresponding `th`/`td` set via a `hidden` class; at least one column must remain visible (the button for the last visible column is disabled).
- Selection persists in localStorage under `navidrome-history-columns` via `js/prefs.js` helpers; unknown/missing keys default to all columns visible.
- The mobile card layout (≤ 480 px) ignores column visibility and always renders all fields, matching current behavior.
- New i18n keys in `messages-dashboard.js` for all five locales: `history.columns`, `history.column.user`, `history.column.title`, `history.column.artist`, `history.column.album`, `history.column.played`, `history.column.count`.
- `tests/test_static_dashboard.py` covers persistence keys and the minimum-one-column rule.

## 8. Brand icon geometry

### Problem

The extracted mark deviates from the source artwork: the note head is a rotated ellipse instead of a circle, the three sound-wave arcs collide with the outer ring, and the ring/note/flag proportions drift from the reference.

### Design

One shared geometry (viewBox `0 0 128 128`, stroke-linecap/join round) replaces the current paths in all four places: the inline header SVG in `index.html` (CSS-variable colors) and `assets/icon.svg`, `assets/icon-dark.svg`, `src/static/favicon.svg` (fixed palette colors, each keeping its own background/fill/stroke colors).

| Element | Geometry |
|---|---|
| Ring | center (64, 62), r 36.5, stroke 5; arc from (100.1, 56.9) to (87.5, 90.0), large-arc, sweep 0 — gap on the right side |
| Note head | circle at (59, 71), r 8, stroke 5, fill background; center dot r 2.2 |
| Stem | `M 67 71 V 39.5`, stroke 5 |
| Flag | `M 67 39.5 L 82 45.5 V 56.5 L 67 50.5 Z`, fill background, stroke 5 |
| Sound arcs | concentric on (59, 71), radii 13.5 / 20 / 26.5, each from math-angle 128° to 185°, sweep 0, stroke 5, shared gradient `brandWave` (orange → lime → cyan, top-to-bottom) |
| Baseline | `M 69 98.5 H 103`, stroke 4.5 |
| Bars | rects 7 wide, stroke 4.5, bottoms on the baseline: x 70.5 h 9, x 82 h 16.5, x 93.5 h 23 |
| Trend | `M 70.5 86.5 L 81 77.5 L 96.5 66.5`, stroke 4.5, gradient `brandTrend`; nodes r 2.6 / 2.6 / 4.5 at the vertices, stroked orange / lime / cyan |

Arc endpoints (precomputed):

- r 13.5: `M 50.69 60.36 A 13.5 13.5 0 0 0 45.55 72.18`
- r 20: `M 46.69 55.24 A 20 20 0 0 0 39.08 72.74`
- r 26.5: `M 42.68 50.12 A 26.5 26.5 0 0 0 32.60 73.31`

`brandWave`: `linearGradient userSpaceOnUse` from (50, 46) to (38, 74), stops `#F97316` / `#84CC16` (0.5) / `#22D3EE`. The header copy keeps `var(--app-text)` / `var(--app-bg)` strokes; the static files keep their existing palettes.

Verification: rendered side-by-side against the reference artwork at 128 px and 512 px; no stroke intersections between sound arcs and ring (minimum clearance ≈ 0.6 px), note head circular, flag attached flush to the stem.

## Testing

- Python: `pytest tests/test_review.py tests/test_static_settings.py tests/test_static_dashboard.py tests/test_about.py`
- Node: `node --test tests/node/` (i18n parity for new message keys, filters untouched)
- Manual pass: dashboard (header badge, history table, column popover), review page (year popover, three charts, top-list covers with single and multiple servers), settings (row-level test, About version row), icon rendering in both themes.
