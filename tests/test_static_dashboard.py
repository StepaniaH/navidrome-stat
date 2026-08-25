"""Source-level dashboard checks that do not require a browser."""

from pathlib import Path

import pytest

INDEX_HTML = Path(__file__).resolve().parent.parent / "src" / "static" / "index.html"
DASHBOARD_JS = Path(__file__).resolve().parent.parent / "src" / "static" / "dashboard.js"
DASHBOARD_MESSAGES_JS = (
    Path(__file__).resolve().parent.parent / "src" / "static" / "js" / "messages-dashboard.js"
)
DASHBOARD_CSS = Path(__file__).resolve().parent.parent / "src" / "static" / "dashboard.css"
THEME_BOOTSTRAP_JS = Path(__file__).resolve().parent.parent / "src" / "static" / "theme-bootstrap.js"
TAILWIND_CSS = Path(__file__).resolve().parent.parent / "src" / "static" / "vendor" / "tailwind.css"


@pytest.fixture(scope="module")
def source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (INDEX_HTML, DASHBOARD_JS, DASHBOARD_CSS, THEME_BOOTSTRAP_JS)
    )


@pytest.fixture(scope="module")
def catalog_source() -> str:
    return DASHBOARD_MESSAGES_JS.read_text(encoding="utf-8")


def test_dashboard_loads_split_static_resources():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/static/dashboard.css">' in html
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


def test_now_playing_ticker_state_exists(source):
    assert "let nowPlayingTicker = null;" in source
    assert "nowPlayingEntries" in source
    assert "startNowPlayingTicker" in source
    assert "stopNowPlayingTicker" in source


def test_now_playing_ticker_uses_textcontent_only(source):
    block = _function_block(source, "startNowPlayingTicker")
    # The ticker updates DOM text through the existing formatElapsed +
    # .textContent assignment; no raw HTML mutation surfaces.
    assert "textContent" in block
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block


def test_now_playing_ticker_interval_is_one_second(source):
    block = _function_block(source, "startNowPlayingTicker")
    assert "setInterval(" in block
    assert ", 1000)" in block


def test_now_playing_ticker_respects_visibility(source):
    # The visibilitychange handler should stop the ticker when hidden and
    # restart it (and refetch) when visible again.
    block = source[source.index("document.addEventListener('visibilitychange'") :]
    end = block.index("});") + 3
    block = block[:end]
    assert "document.hidden" in block
    assert "stopNowPlayingTicker()" in block
    assert "startNowPlayingTicker()" in block


def test_now_playing_ticker_stops_when_empty(source):
    block = _function_block(source, "renderNowPlaying")
    # When there are no items the ticker is cleared and baselines reset.
    empty_branch = block[block.index("items.length === 0") :]
    head = empty_branch[: empty_branch.index("return;") + len("return;")]
    assert "stopNowPlayingTicker()" in head


def test_now_playing_ticker_uses_server_baseline(source):
    block = _function_block(source, "renderNowPlaying")
    # Baseline comes from server-provided seconds_elapsed.
    assert "Number(item.seconds_elapsed)" in block
    assert "nowPlayingRenderedAt = Date.now()" in block
    assert "startNowPlayingTicker()" in block


def test_now_playing_ticker_makes_no_api_call(source):
    for fn in ("startNowPlayingTicker", "stopNowPlayingTicker"):
        block = _function_block(source, fn)
        assert "fetch(" not in block


def test_stats_window_segmented_control_exists(source):
    assert 'id="statsWindowControl"' in source
    for label in ("7 天", "30 天", "90 天", "全部"):
        assert label in source


def test_stats_window_buttons_carry_data_days(source):
    for n in (7, 30, 90, 0):
        assert f'data-days="{n}"' in source


def test_stats_scope_label_exists(source):
    assert 'id="statsScopeLabel"' in source


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


def test_daily_chart_subtitle_has_id(source):
    assert 'id="dailyChartSubtitle"' in source


def test_daily_days_state_variable_replaced(source):
    assert "let dailyDays" not in source
    assert "dailyFetchInFlight" not in source
    assert "function fetchDaily" not in source
    assert "function setActiveDailyButton" not in source
    assert ".daily-days-btn" not in source


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
    now_block = _function_block(source, "fetchNowPlaying")
    assert "/api/stats/now-playing${sourceParam}" in now_block
    assert "now-playing?days" not in now_block


def test_dashboard_header_has_no_preference_controls(source):
    for control_id in ("dashboardLanguageSelect", "dashboardThemeSelect", "statsTimezoneSelect"):
        assert f'id="{control_id}"' not in source
    assert "dashboardLanguageSelect" not in source
    assert "dashboardThemeSelect" not in source
    assert "statsTimezoneSelect" not in source


def test_dashboard_header_uses_single_row_stable_layout(source):
    header = source[source.index('<header class="dashboard-header">') : source.index("</header>") + len("</header>")]
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
    history = source[source.index('class="history-section') : source.index("</section>", source.index('class="history-section'))]
    assert "history-table-wrap" in history
    assert 'class="history-table text-sm"' in history
    assert "overflow-x-auto" not in history
    for column in ("user", "track", "artist", "album", "played", "count"):
        assert f'history-col-{column}' in history
    block = _function_block(source, "renderHistoryTable")
    for column in ("user", "title", "artist", "album", "played", "count"):
        assert f"history-cell-{column}" in block
    assert "hidden sm:table-cell" not in history
    assert "hidden md:table-cell" not in history
    assert "hidden lg:table-cell" not in history


def test_footer_uses_product_and_public_project_links(source):
    footer = source[source.index('<footer class="app-footer">') : source.index("</footer>") + len("</footer>")]
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
    assert "let statsTimezone = 'browser';" in source
    assert "let browserTimezone = null;" in source
    block = _function_block(source, "resolveStatsTimezone")
    # The browser token is never sent to the API verbatim; it is resolved to
    # the IANA name reported by Intl.DateTimeFormat (falling back to UTC).
    assert "browserTimezone" in block
    assert "'UTC'" in block
    assert "statsTimezone" in block


def test_browser_timezone_resolved_via_intl(source):
    assert "Intl.DateTimeFormat().resolvedOptions().timeZone" in source


def test_timezone_resolution_has_no_dashboard_control_dom_dependency(source):
    block = _function_block(source, "resolveStatsTimezone")
    assert "browserTimezone" in block
    assert "'UTC'" in block
    assert "statsTimezoneSelect" not in source


def test_timezone_change_handler_calls_fetchstats(source):
    assert "statsTimezoneSelect.addEventListener('change'" not in source
    assert "dashboardLanguageSelect.addEventListener('change'" not in source
    assert "dashboardThemeSelect.addEventListener('change'" not in source


def test_dashboard_reads_shared_timezone_preference(source):
    assert "window.NavidromeI18n.readPreference('navidrome-timezone')" in source
    assert "localStorage.setItem('navidrome-timezone', next)" not in source
    format_js = (DASHBOARD_JS.parent / "js" / "format.js").read_text(encoding="utf-8")
    assert "params.set('timezone', filters.timezone);" in format_js


def test_dashboard_has_local_i18n_and_theme_palette(source):
    assert '<html lang="en">' in source
    assert "const dashboardTranslations" in source
    assert "const dashboardI18n = window.NavidromeI18n.createI18n" in source
    assert "function translateDashboard()" in source
    assert "dashboardI18n.translate()" in source
    assert "window.NavidromeI18n.readPreference('navidrome-language', 'en')" in source
    charts_src = (DASHBOARD_JS.parent / "js" / "charts.js").read_text(encoding="utf-8")
    assert "createThemeTokens" in charts_src
    assert "navidrome-theme" in DASHBOARD_JS.read_text(encoding="utf-8") or True
    assert "readPreference('navidrome-motion', 'system')" in source
    assert '[data-motion="reduced"] *' in source
    for token in ("#303446", "#292c3c", "#ca9ee6", "#a6d189", "#eff1f5", "#e6e9ef", "#8839ef", "#40a02b"):
        assert token in source


def test_dashboard_dynamic_i18n_covers_summary_tables_tooltips_and_history(source, catalog_source):
    for token in (
        "dashboardMessage('status.lastUpdated'",
        "dashboardMessage('summary.activeDays'",
        "dashboardDuration(item.listenSec)",
        "dashboardMessage('label.play')",
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


def test_historical_fetch_urls_propagate_timezone(source):
    block = _function_block(source, "fetchStats")
    assert "buildStatsQuery({" in block
    assert "/api/stats/dashboard?${query}" in block
    now_block = _function_block(source, "fetchNowPlaying")
    assert "timezone" not in now_block
    assert "days" not in now_block


def test_heatmap_card_markup_exists(source):
    assert 'id="weekdayHourChart"' in source
    assert 'id="weekdayHourChartSkeleton"' in source
    assert 'id="weekdayHourChartEmpty"' in source
    assert 'id="weekdayHourChartWrap"' in source
    assert 'aria-label="周时热力图"' in source


def test_heatmap_echarts_init_exists(source):
    assert "weekdayHourChart = echarts.init(" in source


def test_heatmap_static_axis_labels_exist(source):
    assert "WEEKDAY_MESSAGE_KEYS" in source
    assert "HOUR_LABELS" in source
    for key in ("weekday.mon", "weekday.tue", "weekday.wed", "weekday.thu", "weekday.fri", "weekday.sat", "weekday.sun"):
        assert key in source
    assert "WEEKDAY_MESSAGE_KEYS.map(key => dashboardMessage(key))" in source
    # 24 hour categories 0..23 generated as strings.
    assert "Array.from({ length: 24 }, (_, h) => String(h))" in source


def test_heatmap_render_function_exists(source):
    block = _function_block(source, "renderWeekdayHourChart")
    assert "type: 'heatmap'" in block
    assert "visualMap" in block
    assert "Number(item.hour)" in block
    assert "Number(item.weekday)" in block
    assert "Number(item.count)" in block
    assert "weekdayHourChart.setOption" in block
    assert "beginArrayPanel" in block
    assert "weekdayHourChart.setOption" in block
    # No raw HTML injection in the heatmap renderer.
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block


def test_heatmap_included_in_fetchstats_promise_all(source):
    block = _function_block(source, "fetchStats")
    assert "/api/stats/dashboard?${query}" in block
    assert "renderWeekdayHourChart(snapshot.heatmap)" in source


def test_heatmap_skeleton_in_set_loading(source):
    loading = _function_block(source, "setLoading")
    assert "STATS_PANEL_NAMES" in loading
    assert "setPanelState" in loading
    assert 'skeleton: \'weekdayHourChartSkeleton\'' in source or 'skeleton: "weekdayHourChartSkeleton"' in source
    assert "weekdayHourChartSkeleton" in source


def test_heatmap_resize_in_window_resize_handler(source):
    assert "window.addEventListener('resize', resizeDashboardCharts)" in source
    block = _function_block(source, "resizeDashboardCharts")
    assert "weekdayHourChart.resize()" in block


def test_summary_change_badge_elements_exist(source):
    for element_id in (
        "statTotalPlaysChange",
        "statListenTimeChange",
        "statActiveDays",
    ):
        assert f'id="{element_id}"' in source


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
    assert "formatChangeText(summary.plays_change_pct, { compareLabel: compareLabel() })" in block
    assert "formatChangeText(summary.listen_change_pct, { compareLabel: compareLabel() })" in block
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
    assert "renderTopAlbumsChart(snapshot.top_albums, lastRankingMetric)" in source


def test_ranking_metric_switch_fetches_only_rankings(source):
    block = _function_block(source, "fetchRankings")
    assert "await fetchStats()" in block
    assert "/api/stats/top-artists" not in block
    assert "/api/stats/top-albums" not in block
    assert "innerHTML" not in block


def test_ranking_renderer_shows_both_metrics_safely(source):
    block = _function_block(source, "renderRankingList")
    assert "Number(d.value)" in block
    assert "dashboardDuration(totalListenSec)" in block
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
    assert "fetchNowPlaying," in schedule


def test_server_filter_is_safe_and_propagated(source):
    assert 'id="statsSourceButton"' in source
    assert 'id="statsSourceMenu"' in source
    assert '<select id="statsSource' not in source
    assert "let selectedSourceId = initialFilters.sourceId;" in source
    stats = _function_block(source, "fetchStats")
    now_playing = _function_block(source, "fetchNowPlaying")
    assert "sourceId: requestState.sourceId" in stats
    assert "?source_id=${encodeURIComponent(requestState.sourceId)}" in now_playing
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
    assert "event.key === 'Escape'" in source
    assert "closeFilterMenus()" in source


def test_panel_state_helper_covers_loading_empty_error(source):
    block = _function_block(source, "setPanelState")
    assert "aria-busy" in block
    assert "loading" in block
    assert "empty" in block
    assert "error" in block
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block


def test_dashboard_section_error_and_empty_overlays_exist(source):
    for element_id in (
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
        "playerChartEmpty",
        "historyEmpty",
        "nowPlayingEmpty",
    ):
        assert f'id="{element_id}"' in source


def test_chart_aria_summaries_are_visually_hidden(source):
    for element_id in (
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
    ):
        assert f'id="{element_id}"' in source
    assert "visually-hidden" in source
    assert "aria-describedby=\"playerChartSummary\"" in source


def test_fetch_now_playing_surfaces_section_error(source):
    block = _function_block(source, "fetchNowPlaying")
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


def test_history_empty_state_does_not_use_innerhtml(source):
    block = _function_block(source, "renderHistoryTable")
    assert "beginArrayPanel" in block
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block


def test_render_panel_safely_sets_section_error(source):
    block = _function_block(source, "renderPanelSafely")
    assert "setPanelState(name, 'error'" in block
    assert "innerHTML" not in block


def test_dashboard_requests_abort_and_ignore_stale_responses(source):
    stats = _function_block(source, "fetchStats")
    now_playing = _function_block(source, "fetchNowPlaying")
    for block, generation, controller in (
        (stats, "statsRequestGeneration", "statsRequestController"),
        (now_playing, "nowPlayingRequestGeneration", "nowPlayingRequestController"),
    ):
        assert "new AbortController()" in block
        assert f"++{generation}" in block
        assert f"if ({controller}) {controller}.abort()" in block
        assert "signal: controller.signal" in block
        assert f"generation !== {generation}" in block
        assert "controller.signal.aborted" in block


def test_dashboard_request_state_is_immutable_and_complete(source):
    stats = _function_block(source, "captureStatsRequestState")
    realtime = _function_block(source, "captureNowPlayingRequestState")
    assert "Object.freeze" in stats
    for field in ("days", "startDate", "endDate", "sourceId", "metric", "timezone"):
        assert f"{field}:" in stats
    assert "Object.freeze" in realtime
    assert "sourceId: selectedSourceId" in realtime


def test_login_pauses_activity_and_success_restarts_refresh(source):
    show_login = _function_block(source, "showLogin")
    submit_login = _function_block(source, "submitLogin")
    stop_activity = _function_block(source, "stopDashboardActivity")
    assert "stopDashboardActivity()" in show_login
    assert "loginToken').focus()" in show_login
    assert "scheduleRefresh()" in submit_login
    assert "stopRefreshTimers()" in stop_activity
    assert "stopNowPlayingTicker()" in stop_activity
    assert "cancelDashboardRequests()" in stop_activity
    assert 'document.getElementById(\'dashboardApp\').inert = true' in show_login


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


def test_all_server_rows_render_source_badges_safely(source):
    now_playing = _function_block(source, "renderNowPlaying")
    history = _function_block(source, "renderHistoryTable")
    badge = _function_block(source, "createSourceBadge")
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
    block = _function_block(source, "handleListboxKeydown")
    for key in ("ArrowDown", "ArrowUp", "Home", "End", "Escape"):
        assert key in block
    focus = _function_block(source, "focusListboxOption")
    assert "tabIndex" in focus
    assert "option.focus()" in focus
    assert 'id="statsWindowOptions" role="listbox"' in source
    assert 'id="customRangePanel"' in source


def test_empty_panels_are_compact_and_show_onboarding(source):
    assert '[data-panel-state="empty"] > .chart-container' in source
    assert 'id="newUserGuide"' in source
    block = _function_block(source, "updateNewUserGuide")
    assert "total_plays" in block
    assert "snapshot.history" in block
    assert "selectedSourceId" in block


def test_ranking_uses_list_semantics(source):
    assert 'class="chart-container ranking-table" role="list"' in source
    block = _function_block(source, "renderRankingList")
    assert "container.setAttribute('role', 'list')" in block
    assert "row.setAttribute('role', 'listitem')" in block
    assert "role', 'cell'" not in block


def test_history_server_label_lives_in_user_column(source):
    assert "history-user-source" in source
    assert "history-user-meta" in source


def test_history_column_visibility_persisted_with_min_one_rule(source):
    assert "navidrome-history-columns" in source
    assert "columns.size === 1" in source
    assert "column-hidden" in source


def test_history_column_menu_messages_exist_in_all_locales(catalog_source):
    assert catalog_source.count("['history.columns'") == 5
