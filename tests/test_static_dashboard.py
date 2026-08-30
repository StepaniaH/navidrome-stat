"""Source-level dashboard checks that do not require a browser."""

from pathlib import Path

import pytest

INDEX_HTML = Path(__file__).resolve().parent.parent / "src" / "static" / "index.html"
DASHBOARD_JS = Path(__file__).resolve().parent.parent / "src" / "static" / "dashboard.js"
DASHBOARD_MODULE_DIR = DASHBOARD_JS.parent / "js" / "dashboard"
NOW_PLAYING_JS = DASHBOARD_MODULE_DIR / "now-playing.js"
HISTORY_JS = DASHBOARD_MODULE_DIR / "history.js"
PLAY_ACCOUNTING_JS = DASHBOARD_MODULE_DIR / "play-accounting.js"
HISTORICAL_DASHBOARD_JS = DASHBOARD_MODULE_DIR / "historical-dashboard.js"
LOCALES_DIR = Path(__file__).resolve().parent.parent / "src" / "static" / "js" / "i18n" / "locales"
DASHBOARD_CSS = Path(__file__).resolve().parent.parent / "src" / "static" / "dashboard.css"
LISTBOX_JS = Path(__file__).resolve().parent.parent / "src" / "static" / "js" / "listbox.js"
AUTH_JS = Path(__file__).resolve().parent.parent / "src" / "static" / "js" / "auth.js"
THEME_BOOTSTRAP_JS = (
    Path(__file__).resolve().parent.parent / "src" / "static" / "theme-bootstrap.js"
)
THEMES_CSS = Path(__file__).resolve().parent.parent / "src" / "static" / "themes.css"
TAILWIND_CSS = Path(__file__).resolve().parent.parent / "src" / "static" / "vendor" / "tailwind.css"


@pytest.fixture(scope="module")
def source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            INDEX_HTML,
            DASHBOARD_JS,
            NOW_PLAYING_JS,
            HISTORY_JS,
            PLAY_ACCOUNTING_JS,
            HISTORICAL_DASHBOARD_JS,
            DASHBOARD_CSS,
            THEMES_CSS,
            THEME_BOOTSTRAP_JS,
        )
    )


@pytest.fixture(scope="module")
def now_playing_source() -> str:
    return NOW_PLAYING_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def play_accounting_source() -> str:
    return PLAY_ACCOUNTING_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def history_source() -> str:
    return HISTORY_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def catalog_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(LOCALES_DIR.glob("*.js")))


def test_dashboard_loads_split_static_resources():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/static/dashboard.css">' in html
    assert '<link rel="stylesheet" href="/static/themes.css">' in html
    assert '<script type="module" src="/static/dashboard.js"></script>' in html
    assert '<script type="module" src="/static/theme-bootstrap.js"></script>' in html
    assert '<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">' in html
    assert "<style>" not in html
    assert html.count("<script>") == 0


def test_generated_tailwind_contains_dynamic_dashboard_state_classes():
    stylesheet = TAILWIND_CSS.read_text(encoding="utf-8")
    assert ".bg-red-400" in stylesheet
    assert ".animate-pulse" in stylesheet
    assert ".invisible" in stylesheet


def _function_block(source: str, fn_name: str) -> str:
    start = source.index(f"function {fn_name}(")
    i = source.index("(", start)
    paren_depth = 0
    while i < len(source):
        ch = source[i]
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
            if paren_depth == 0:
                break
        i += 1
    brace_open = source.index("{", i)
    depth = 0
    j = brace_open
    while j < len(source):
        ch = source[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : j + 1]
        j += 1
    raise AssertionError(f"function {fn_name} not balanced")


def test_dashboard_behaviors_are_composed_through_small_module_interfaces():
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    for factory in (
        "createNowPlaying",
        "createHistory",
        "createPlayAccounting",
        "createHistoricalDashboard",
    ):
        assert f"import {{ {factory} }}" in source
    assert "nowPlaying.refresh()" in source
    assert "history.render(" in source
    assert "playAccounting.mount()" in source
    assert "historicalDashboard.render(" in source


def test_now_playing_ticker_state_exists(now_playing_source):
    assert "let ticker = null;" in now_playing_source
    assert "renderedEntries" in now_playing_source
    assert "startTicker" in now_playing_source
    assert "stopTicker" in now_playing_source


def test_now_playing_ticker_uses_textcontent_only(now_playing_source):
    block = _function_block(now_playing_source, "startTicker")
    # The ticker updates DOM text through the existing formatElapsed +
    # .textContent assignment; no raw HTML mutation surfaces.
    assert "textContent" in block
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block


def test_now_playing_ticker_interval_is_one_second(now_playing_source):
    block = _function_block(now_playing_source, "startTicker")
    assert "setInterval(" in block
    assert ", 1000)" in block


def test_now_playing_ticker_respects_visibility(source):
    # The visibilitychange handler should stop the ticker when hidden and
    # restart it (and refetch) when visible again.
    block = source[source.index("document.addEventListener('visibilitychange'") :]
    end = block.index("});") + 3
    block = block[:end]
    assert "document.hidden" in block
    assert "nowPlaying.stopTicker()" in block
    assert "nowPlaying.startTicker()" in block


def test_now_playing_ticker_stops_when_empty(now_playing_source):
    block = _function_block(now_playing_source, "render")
    # When there are no items the ticker is cleared and baselines reset.
    empty_branch = block[block.index("items.length === 0") :]
    head = empty_branch[: empty_branch.index("return;") + len("return;")]
    assert "stopTicker()" in head


def test_now_playing_ticker_uses_server_baseline(now_playing_source):
    block = _function_block(now_playing_source, "render")
    # Baseline comes from server-provided seconds_elapsed.
    assert "Number(item.seconds_elapsed)" in block
    assert "renderedAt = Date.now()" in block
    assert "startTicker()" in block


def test_now_playing_ticker_makes_no_api_call(now_playing_source):
    for fn in ("startTicker", "stopTicker"):
        block = _function_block(now_playing_source, fn)
        assert "fetch(" not in block


def test_stats_window_segmented_control_exists(source):
    assert 'id="statsWindowControl"' in source
    for label in ("7 天", "30 天", "90 天", "全部"):
        assert label in source


def test_stats_window_buttons_carry_data_days(source):
    for n in (7, 30, 90, 0):
        assert f'data-days="{n}"' in source


@pytest.mark.parametrize(
    "element_id",
    [
        # stats scope / subtitle
        "statsScopeLabel",
        "dailyChartSubtitle",
        # heatmap card markup
        "weekdayHourChart",
        "weekdayHourChartSkeleton",
        "weekdayHourChartEmpty",
        "weekdayHourChartWrap",
        # summary change badges
        "statTotalPlaysChange",
        "statListenTimeChange",
        "statActiveDays",
        # section error overlays
        "nowPlayingError",
        "playerChartError",
        "transcodingChartError",
        "hourlyChartError",
        "dailyChartError",
        "weekdayHourChartError",
        "topArtistsChartError",
        "topAlbumsChartError",
        "serverSourceError",
        "historyError",
        "summaryError",
        # section empty states
        "playerChartEmpty",
        "historyEmpty",
        "nowPlayingEmpty",
        # visually hidden chart aria summaries
        "playerChartSummary",
        "transcodingChartSummary",
        "hourlyChartSummary",
        "dailyChartSummary",
        "weekdayHourChartSummary",
        "topArtistsChartSummary",
        "topAlbumsChartSummary",
        "nowPlayingSummary",
        "historySummary",
        "summaryAria",
        # on-demand playback accounting details
        "playAccountingButton",
        "playAccountingPanel",
        "playAccountingValue",
        "playAccountingRetry",
    ],
)
def test_dashboard_element_ids_exist(source, element_id):
    assert f'id="{element_id}"' in source


def test_dashboard_markup_accessibility_annotations_exist(source):
    assert 'aria-label="周时热力图"' in source
    assert "visually-hidden" in source
    assert 'aria-describedby="playerChartSummary"' in source


def test_stats_window_label_helper(source):
    block = _function_block(source, "statsWindowLabel")
    assert "dashboardMessage('window.allLabel')" in block
    assert "dashboardMessage('window.daysLabel', { days: statsDays })" in block


def test_stats_window_button_click_updates_state_and_calls_fetch(source):
    block = source[source.index("document.querySelectorAll('.stats-window-option')") :]
    end = block.index("setActiveStatsWindowButton(statsDays);")
    block = block[:end]
    assert "addEventListener('click'" in block
    assert "statsDays = days" in block
    assert "fetchStats()" in block
    assert "fetchDaily" not in block


def test_stats_window_subtitle_updates_to_selected_range(source):
    block = _function_block(source, "setActiveStatsWindowButton")
    assert "dashboardMessage('daily.subtitle'" in block
    assert "window: statsWindowLabel()" in block


def test_historical_fetch_urls_use_stats_days(source):
    block = _function_block(source, "fetchStats")
    assert "/api/stats/dashboard?${query}" in block
    assert "buildStatsQuery({" in block
    assert "captureStatsRequestState()" in block
    for endpoint in (
        "summary?",
        "players?",
        "transcoding?",
        "hourly?",
        "daily?",
        "history?",
        "top-artists?",
        "top-albums?",
    ):
        assert f"/api/stats/{endpoint}" not in block
    now_block = _function_block(NOW_PLAYING_JS.read_text(encoding="utf-8"), "refresh")
    assert "/api/stats/now-playing${sourceParam}" in now_block
    assert "timezone" not in now_block
    assert "days" not in now_block


def test_playback_accounting_is_lazy_and_uses_dashboard_scope(play_accounting_source):
    block = _function_block(play_accounting_source, "refresh")
    assert "buildStatsScopeQuery(getScope())" in block
    assert "/api/stats/short-plays?${query}" in block
    assert "playAccountingValue').textContent" in play_accounting_source
    assert "refresh();" in _function_block(play_accounting_source, "mount")


def test_dashboard_header_has_no_preference_controls(source):
    assert "dashboardLanguageSelect" not in source
    assert "dashboardThemeSelect" not in source
    assert "statsTimezoneSelect" not in source


def test_dashboard_header_uses_single_row_stable_layout(source):
    header = source[
        source.index('<header class="dashboard-header">') : source.index("</header>")
        + len("</header>")
    ]
    for class_name in (
        "dashboard-header-main",
        "dashboard-brand",
        "dashboard-filters",
        "dashboard-meta",
        "dashboard-actions",
        "filter-trigger-value",
    ):
        assert class_name in header
    assert 'class="visually-hidden"' in header
    assert "dashboard-toolbar" not in header
    assert "dashboard-eyebrow" not in header
    assert "dashboard-subtitle" not in header
    assert "lg:grid-cols-[" not in header
    assert "text-[10px]" not in header


def test_history_table_has_no_horizontal_scroll_container(source):
    history = source[
        source.index('class="history-section') : source.index(
            "</section>", source.index('class="history-section')
        )
    ]
    assert "history-table-wrap" in history
    assert 'class="history-table text-sm"' in history
    assert "overflow-x-auto" not in history
    for column in ("user", "track", "artist", "album", "played", "count"):
        assert f"history-col-{column}" in history
    block = _function_block(HISTORY_JS.read_text(encoding="utf-8"), "render")
    for column in ("user", "title", "artist", "album", "played", "count"):
        assert f"history-cell-{column}" in block
    assert "hidden sm:table-cell" not in history
    assert "hidden md:table-cell" not in history
    assert "hidden lg:table-cell" not in history


def test_footer_uses_product_and_public_project_links(source):
    footer = source[
        source.index('<footer class="app-footer">') : source.index("</footer>") + len("</footer>")
    ]
    assert "Navidrome Stat" in footer
    assert 'href="https://github.com/StepaniaH/navidrome-stat"' in footer
    assert 'href="https://github.com/StepaniaH/navidrome-stat/blob/main/LICENSE"' in footer
    assert footer.count('target="_blank"') == 2
    assert footer.count('rel="noopener noreferrer"') == 2
    assert "正在播放每 10 秒刷新" not in source
    assert "Now playing refreshes every 10s" not in source


def test_dashboard_status_preserves_header_dot_class(source):
    block = _function_block(source, "setStatus")
    assert "dot.className = 'dashboard-live-dot '" in block
    assert "w-2 h-2 rounded-full" not in block


def test_timezone_state_and_resolver_exist(source):
    # Global state declared near the other dashboard state variables.
    assert "let statsTimezone = hasSharedTimezone ? initialFilters.timezone : 'browser';" in source
    assert "new URLSearchParams(window.location.search).has('timezone')" in source
    assert "let browserTimezone = null;" in source
    block = _function_block(source, "resolveStatsTimezone")
    # The browser token is never sent to the API verbatim; it is resolved to
    # the IANA name reported by Intl.DateTimeFormat (falling back to UTC).
    assert "browserTimezone" in block
    assert "'UTC'" in block
    assert "statsTimezone" in block
    # The browser timezone is resolved through Intl, never sent verbatim.
    assert "Intl.DateTimeFormat().resolvedOptions().timeZone" in source


def test_dashboard_reads_shared_timezone_preference(source):
    assert "readPreference('navidrome-timezone')" in source
    assert "localStorage.setItem('navidrome-timezone', next)" not in source
    format_js = (DASHBOARD_JS.parent / "js" / "format.js").read_text(encoding="utf-8")
    assert "params.set('timezone', filters.timezone);" in format_js


def test_dashboard_has_local_i18n_and_theme_palette(source):
    assert '<html lang="en">' in source
    assert "pageMessages('dashboard', 'review')" in source
    assert "const dashboardI18n = createI18n({" in source
    assert "function translateDashboard()" in source
    assert "dashboardI18n.translate()" in source
    assert "readPreference('navidrome-language', 'en')" in source
    charts_src = (DASHBOARD_JS.parent / "js" / "charts.js").read_text(encoding="utf-8")
    assert "createThemeTokens" in charts_src
    dashboard_script = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "THEME_CHANGE_EVENT" in dashboard_script
    assert "window.addEventListener(THEME_CHANGE_EVENT" in dashboard_script
    assert "readPreference('navidrome-motion', 'system')" in source
    assert '[data-motion="reduced"] *' in source
    theme_css = THEMES_CSS.read_text(encoding="utf-8")
    for token in (
        "--page-bg:",
        "--text:",
        "--accent:",
        "--app-on-accent:",
        "--chart-1:",
        "--chart-8:",
    ):
        assert token in theme_css


def test_dashboard_dynamic_i18n_covers_summary_tables_tooltips_and_history(source, catalog_source):
    for token in (
        "dashboardMessage('status.lastUpdated'",
        "t('summary.activeDays'",
        "formatDuration(item.listenSec)",
        "t('label.play')",
        "dashboardMessage('daily.subtitle'",
    ):
        assert token in source
    for entry in (
        "['client.detailTitle', 'Client listening details']",
        "['client.listeningTime', 'Listening time']",
        "['subtitle.serverBreakdown',",
        "['subtitle.history',",
        "['history.caption',",
        "['history.lastPlayed',",
        "['metric.listenTime',",
    ):
        assert entry in catalog_source
    assert "function dashboardText(" not in source


def test_heatmap_static_axis_labels_exist(source):
    assert "WEEKDAY_MESSAGE_KEYS" in source
    assert "HOUR_LABELS" in source
    for key in (
        "weekday.mon",
        "weekday.tue",
        "weekday.wed",
        "weekday.thu",
        "weekday.fri",
        "weekday.sat",
        "weekday.sun",
    ):
        assert key in source
    assert "WEEKDAY_MESSAGE_KEYS.map((key) => t(key))" in source
    # 24 hour categories 0..23 generated as strings.
    assert "Array.from({ length: 24 }, (_, hour) => String(hour))" in source


def test_heatmap_render_function_exists(source):
    assert "weekdayHourChart = echarts.init(" in source
    block = _function_block(source, "renderWeekdayHourChart")
    assert "type: 'heatmap'" in block
    assert "visualMap" in block
    assert "Number(item.hour)" in block
    assert "Number(item.weekday)" in block
    assert "Number(item.count)" in block
    assert "weekdayHourChart.setOption" in block
    # The color slider sits below the hour axis without colliding with labels.
    assert "bottom: 80" in block
    assert "heatmapRamp()" in block
    assert "inverse: true" in block
    assert "borderRadius: 3, borderWidth: 2, borderColor: 'transparent'" in block
    assert "beginArrayPanel" in block
    # No raw HTML injection in the heatmap renderer.
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block
    # The heatmap render is wired into the fetchStats snapshot dispatch.
    assert "renderWeekdayHourChart(snapshot.heatmap)" in source


def test_heatmap_skeleton_in_set_loading(source):
    loading = _function_block(source, "setLoading")
    assert "STATS_PANEL_NAMES" in loading
    assert "setPanelState" in loading
    assert (
        "skeleton: 'weekdayHourChartSkeleton'" in source
        or 'skeleton: "weekdayHourChartSkeleton"' in source
    )


def test_heatmap_resize_in_window_resize_handler(source):
    assert "window.addEventListener('resize', historicalDashboard.resize)" in source
    block = _function_block(source, "resizeDashboardCharts")
    assert "weekdayHourChart," in source[source.index("const charts = [") :]
    # Resize is skipped when the size already matches so update animations
    # are not interrupted by the post-render resize pass.
    assert "chart.getWidth() !== dom.clientWidth" in block


def test_format_change_text_helper_exists(source, catalog_source):
    format_js = (DASHBOARD_JS.parent / "js" / "format.js").read_text(encoding="utf-8")
    assert "export function formatChangeText" in format_js
    assert "compareLabel" in format_js
    # No raw HTML injection anywhere in the formatter module.
    assert "innerHTML" not in format_js
    assert "insertAdjacentHTML" not in format_js


def test_update_summary_populates_change_badges(source):
    block = _function_block(source, "updateSummary")
    assert "statTotalPlaysChange" in block
    assert "statListenTimeChange" in block
    assert "statActiveDays" in block
    assert block.count("formatChangeText(") == 2
    assert "summary.plays_change_pct" in block
    assert "summary.listen_change_pct" in block
    assert block.count("compareLabel: compareLabel()") == 2
    assert "summary.active_days" in block
    assert "summary.average_daily_plays" in block
    # No innerHTML/outerHTML mutation in summary rendering.
    assert "innerHTML" not in block
    assert "outerHTML" not in block


def test_ranking_metric_control_and_state_exist(source):
    assert 'id="rankingMetricControl"' in source
    assert 'data-ranking-metric="plays"' in source
    assert 'data-ranking-metric="listen_time"' in source
    assert "let rankingMetric = initialFilters.metric;" in source
    assert "rankingInFlight" not in source


def test_ranking_fetch_propagates_metric_and_uses_selected_value(source):
    block = _function_block(source, "fetchStats")
    assert "metric: requestState.metric" in block
    assert "renderStatPanels(snapshot);" in block
    assert "renderPanelSafely" not in block  # dispatch lives in the helper now
    assert "renderTopArtistsChart(snapshot.top_artists, metric)" in source
    assert "renderTopAlbumsChart(snapshot.top_albums, metric)" in source


def test_ranking_covers_prefer_the_row_source(source):
    assert "sourceId: item.source_id || sourceId" in source


def test_ranking_metric_switch_fetches_only_rankings(source):
    block = _function_block(source, "fetchRankings")
    assert "await fetchStats()" in block
    assert "/api/stats/top-artists" not in block
    assert "/api/stats/top-albums" not in block
    assert "innerHTML" not in block


def test_ranking_renderer_shows_both_metrics_safely(source):
    block = _function_block(source, "renderRankingList")
    assert "Number(item.value)" in block
    assert "formatDuration(totalListenSec)" in block
    assert "textContent" in block
    assert "innerHTML" not in block


def test_client_legend_and_transcoding_percentages_exist(source):
    player_block = _function_block(source, "renderPlayerChart")
    assert "playerChartLegend" in player_block
    assert "player-legend-table" in player_block
    assert "average_listen_sec" in player_block
    assert "transcoding_rate_pct" in player_block
    assert "textContent" in player_block
    assert "innerHTML" not in player_block
    assert "escapeHtml(params.name" in player_block
    fmt_src = (DASHBOARD_JS.parent / "js" / "format.js").read_text(encoding="utf-8")
    assert "export function escapeHtml(" in fmt_src

    transcode_block = _function_block(source, "renderTranscodingChart")
    assert "playsPct" in transcode_block
    assert "listenPct" in transcode_block
    assert "listenSec" in transcode_block
    assert "tooltip" in transcode_block


def test_realtime_and_historical_refresh_are_split(source):
    assert "const REFRESH_MS = 60000;" in source
    assert "const HIDDEN_REFRESH_MS = 300000;" in source
    assert "const NOW_PLAYING_REFRESH_MS = 10000;" in source
    schedule = _function_block(source, "scheduleRefresh")
    assert "fetchStats," in schedule
    assert "nowPlaying.refresh," in schedule


def test_server_filter_is_safe_and_propagated(source):
    assert 'id="statsSourceButton"' in source
    assert 'id="statsSourceMenu"' in source
    assert '<select id="statsSource' not in source
    assert "let selectedSourceId = initialFilters.sourceId;" in source
    stats = _function_block(source, "fetchStats")
    now_playing = _function_block(NOW_PLAYING_JS.read_text(encoding="utf-8"), "refresh")
    assert "sourceId: requestState.sourceId" in stats
    assert "?source_id=${encodeURIComponent(scope.sourceId)}" in now_playing
    options = _function_block(source, "renderSourceOptions")
    assert "textContent" in options
    assert "innerHTML" not in options


def test_custom_date_range_is_validated_and_propagated(source):
    assert 'id="customStartDate"' in source
    assert 'id="customEndDate"' in source
    assert 'data-range="custom"' in source
    fmt = (DASHBOARD_JS.parent / "js" / "format.js").read_text(encoding="utf-8")
    assert "range.tooLong" in fmt and "validateCustomRange" in fmt
    stats = _function_block(source, "fetchStats")
    assert "startDate: requestState.startDate" in stats
    assert "endDate: requestState.endDate" in stats


def test_filter_popovers_have_accessible_keyboard_behavior(source):
    assert 'aria-haspopup="listbox"' in source
    assert 'role="listbox"' in source
    assert 'role="option"' in source
    assert "createListbox({" in source
    assert "attachPopover({" in source


def test_user_filter_shares_the_source_filter_pipeline(source):
    assert 'id="statsUserControl"' in source
    assert 'id="statsUserButton"' in source
    assert 'id="statsUserMenu"' in source
    assert 'data-i18n="user.all"' in source
    assert 'aria-controls="statsUserMenu"' in source
    block = _function_block(source, "renderUserOptions")
    assert "dataset.username" in block
    assert "dashboardMessage('user.all')" in block
    wiring = _function_block(source, "fetchUserOptions")
    assert "/api/stats/users" in wiring
    assert "knownUsers" in source
    assert "statsUserButton" in source
    assert "selectedUsername = name;" in source
    assert "username: selectedUsername" in source
    fetch_block = _function_block(source, "fetchStats")
    assert "username: requestState.username" in fetch_block
    assert "item.username === scope.username" in source


def test_panel_state_helper_covers_loading_empty_error(source):
    block = _function_block(source, "setPanelState")
    assert "aria-busy" in block
    assert "loading" in block
    assert "empty" in block
    assert "error" in block
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block


def test_fetch_now_playing_surfaces_section_error(now_playing_source):
    block = _function_block(now_playing_source, "refresh")
    assert "setPanelState('nowPlaying', 'error'" in block
    assert "error.nowPlaying" in block
    assert "innerHTML" not in block


def test_fetch_stats_isolates_panel_render_failures(source):
    block = _function_block(source, "renderStatPanels")
    assert "renderPanelSafely" in block
    fetch_block = _function_block(source, "fetchStats")
    assert "hasLoadedOnce" in fetch_block
    assert "STATS_PANEL_NAMES.forEach" in fetch_block
    assert "innerHTML" not in block


def test_history_empty_state_does_not_use_innerhtml(history_source):
    block = _function_block(history_source, "render")
    assert "beginArrayPanel" in block
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block


def test_render_panel_safely_sets_section_error(source):
    block = _function_block(source, "renderPanelSafely")
    assert "setPanelState(name, 'error'" in block
    assert "innerHTML" not in block


def test_dashboard_requests_abort_and_ignore_stale_responses(source, now_playing_source):
    stats = _function_block(source, "fetchStats")
    now_playing = _function_block(now_playing_source, "refresh")
    for block, generation, controller in (
        (stats, "statsRequestGeneration", "statsRequestController"),
        (now_playing, "requestGeneration", "requestController"),
    ):
        assert "new AbortController()" in block
        assert f"++{generation}" in block
        assert f"if ({controller}) {controller}.abort()" in block
        assert "signal: controller.signal" in block
        assert f"generation !== {generation}" in block
        assert "controller.signal.aborted" in block


def test_dashboard_request_state_is_immutable_and_complete(source, now_playing_source):
    stats = _function_block(source, "captureStatsRequestState")
    assert "Object.freeze" in stats
    for field in ("days", "startDate", "endDate", "sourceId", "username", "metric", "timezone"):
        assert f"{field}:" in stats
    realtime = _function_block(now_playing_source, "refresh")
    assert "Object.freeze({ ...getScope() })" in realtime


def test_login_pauses_activity_and_success_restarts_refresh(source):
    dashboard = DASHBOARD_JS.read_text(encoding="utf-8")
    auth = AUTH_JS.read_text(encoding="utf-8")
    login_config = dashboard[
        dashboard.index("const login = createLoginController") : dashboard.index(
            "function showLogin"
        )
    ]
    refresh_after_login = _function_block(dashboard, "refreshAfterLogin")
    stop_activity = _function_block(source, "stopDashboardActivity")
    assert "stopDashboardActivity()" in login_config
    assert "inertSelector: '#dashboardApp'" in login_config
    assert "useHiddenClass: true" in login_config
    assert "scheduleRefresh()" in refresh_after_login
    assert "login.bind()" in dashboard
    assert "shell().inert" in auth
    assert "requestAnimationFrame" in auth
    assert "function trapTab" in auth
    assert "stopRefreshTimers()" in stop_activity
    assert "nowPlaying.stopTicker()" in stop_activity
    assert "cancelDashboardRequests()" in stop_activity


def test_source_options_replace_with_available_and_historical_union(source):
    block = _function_block(source, "updateSourceOptions")
    assert "...sourceGroups" in block
    assert "item.source_id || item.id" in block
    assert "item.source_name || item.display_name" in block
    assert "knownSources.clear()" in block
    assert "!knownSources.has(selectedSourceId)" in block
    stats = _function_block(source, "fetchStats")
    assert "snapshot.available_servers" in stats
    assert "snapshot.servers" in stats


def test_all_server_rows_render_source_badges_safely(now_playing_source, history_source):
    now_playing = _function_block(now_playing_source, "render")
    history = _function_block(history_source, "render")
    badge = _function_block(now_playing_source, "createSourceBadge")
    assert "showSources" in now_playing
    assert "createSourceBadge(item)" in now_playing
    assert "showSources" in history
    assert "createSourceLabel(item)" in history
    assert "textContent" in badge
    assert "innerHTML" not in badge


def test_dashboard_accessible_labels_are_bilingual(source, catalog_source):
    for key in (
        "aria.windowListbox",
        "aria.sourceListbox",
        "aria.rankingMetric",
        "aria.serverSources",
        "aria.footerLinks",
        "auth.title",
        "auth.description",
        "auth.token",
        "auth.login",
        "label.directPlay",
        "label.transcoded",
    ):
        assert catalog_source.count(f"['{key}',") >= 2
    assert 'id="loginOverlay"' in source
    assert 'role="dialog"' in source
    assert 'aria-modal="true"' in source
    assert 'data-i18n-attr="aria-label:aria.footerLinks"' in source


def test_filter_listboxes_support_roving_keyboard_focus(source):
    shared = LISTBOX_JS.read_text(encoding="utf-8")
    for key in ("ArrowDown", "ArrowUp", "Home", "End", "Escape", "Tab"):
        assert key in shared
    assert "tabIndex" in shared
    assert "option.focus()" in shared
    assert 'id="statsWindowOptions" role="listbox"' in source
    assert 'id="customRangePanel"' in source


def test_empty_panels_are_compact_and_show_onboarding(source, history_source):
    assert '[data-panel-state="empty"] > .chart-container' in source
    assert 'id="newUserGuide"' in source
    block = _function_block(history_source, "updateFirstUse")
    assert "total_plays" in block
    assert "snapshot.history" in block
    assert "isFiltered()" in block
    assert "[data-history-analysis]" in block
    assert "section.classList.toggle('hidden', firstUse)" in block
    assert "globalHistoryRecordCount" in source
    assert "history.filterEmpty" in source


def test_review_link_carries_server_user_and_timezone_scope(source):
    block = _function_block(source, "syncReviewLink")
    assert "params.set('source_id', selectedSourceId)" in block
    assert "params.set('username', selectedUsername)" in block
    assert "resolveStatsTimezone()" in block


def test_ranking_uses_list_semantics(source):
    assert 'class="chart-container ranking-table" role="list"' in source
    block = _function_block(source, "renderRankingList")
    assert "container.setAttribute('role', 'list')" in block
    assert "row.setAttribute('role', 'listitem')" in block
    # The list carries an accessible label derived from the ranking metric.
    assert "'aria-label', ariaLabel" in block
    assert "role', 'cell'" not in block


def test_history_server_label_lives_in_user_column(source):
    assert "history-user-source" in source
    assert "history-user-meta" in source


def test_history_column_visibility_persisted_with_min_one_rule(source):
    assert "navidrome-history-columns" in source
    assert "columns.size === 1" in source
    assert "column-hidden" in source


def test_history_column_menu_messages_exist_in_all_locales(catalog_source):
    assert catalog_source.count("['history.columns'") == 7


def test_header_shows_brand_name_and_live_version(source):
    assert ">Navidrome Stat</h1>" in source
    assert "data-app-version" in source
    assert 'data-i18n="dashboard.title"' not in source


def test_no_hardcoded_versions_in_frontend():
    for path in (INDEX_HTML, DASHBOARD_JS):
        text = path.read_text(encoding="utf-8")
        assert "0.8." not in text, path


def test_history_column_visibility_reapplied_after_render(history_source):
    # Column hiding must survive every table rebuild (auto-refresh rebuilds
    # all <td>s): a single live Set is re-applied after each render, not just
    # during setup or preference changes.
    assert "let columns = readColumns();" in history_source
    block = _function_block(history_source, "render")
    assert "applyColumns()" in block
    setup = _function_block(history_source, "mount")
    assert "columns = readColumns();" in setup


def test_column_menu_fixes_are_pinned():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    assert '.column-option[aria-pressed="true"] .option-check { opacity: 1; }' in css
    assert ".history-table td.column-hidden { display: none; }" in css
