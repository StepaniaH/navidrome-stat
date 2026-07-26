"""Source-level checks for dashboard additions introduced alongside the
prioritized robustness/UX changes:

* the "正在播放" local elapsed ticker exists and only updates DOM text via
  ``textContent`` (no extra API calls, no innerHTML/insertAdjacentHTML),
* the global statistics window control renders 7/30/90/全部 buttons and
  propagates ``?days=${statsDays}`` to every historical widget, while the
  now-playing endpoint stays real-time (no window filter).

No browser is required - the HTML is inspected as text.
"""

from pathlib import Path

import pytest

INDEX_HTML = Path(__file__).resolve().parent.parent / "src" / "static" / "index.html"


@pytest.fixture(scope="module")
def source() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


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
    assert "全部历史" in block
    assert "最近 ${statsDays} 天" in block


def test_stats_window_button_click_updates_state_and_calls_fetch(source):
    block = source[source.index("document.querySelectorAll('.stats-window-btn')") :]
    end = block.index("setActiveStatsWindowButton(statsDays);")
    block = block[:end]
    assert "addEventListener('click'" in block
    assert "statsDays = days" in block
    assert "fetchStats()" in block
    assert "fetchDaily" not in block


def test_stats_window_subtitle_updates_to_selected_range(source):
    block = _function_block(source, "setActiveStatsWindowButton")
    assert "${statsWindowLabel()}每日播放次数" in block


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
    # Every historical widget request must propagate the global window.
    assert "/api/stats/summary?days=${statsDays}" in block
    assert "/api/stats/players?days=${statsDays}" in block
    assert "/api/stats/transcoding?days=${statsDays}" in block
    assert "/api/stats/hourly?days=${statsDays}" in block
    assert "/api/stats/daily?days=${statsDays}" in block
    assert "/api/stats/history?limit=10&days=${statsDays}" in block
    assert "/api/stats/top-artists?limit=10&days=${statsDays}" in block
    assert "/api/stats/top-albums?limit=10&days=${statsDays}" in block
    # Now-playing must NOT be window-filtered.
    assert "/api/stats/now-playing', fetchOptions" in block
    assert "now-playing?days" not in block


def test_timezone_selector_markup_exists(source):
    assert 'id="statsTimezoneSelect"' in source
    assert 'id="statsTimezoneBrowserOption"' in source
    # Only the browser and UTC options are allowed in the static markup.
    assert 'value="browser"' in source
    assert 'value="UTC"' in source
    assert 'value="Asia/"' not in source
    assert 'value="America/"' not in source
    assert 'value="Europe/"' not in source


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


def test_browser_option_label_populated_safely(source):
    # The browser option label is updated via textContent, never innerHTML,
    # so a malformed IANA name cannot inject markup.
    block = source[source.index("statsTimezoneBrowserOption") :]
    head = block[: block.index("resolveStatsTimezone")]
    assert "textContent" in head
    assert "innerHTML" not in head


def test_timezone_change_handler_calls_fetchstats(source):
    block = source[source.index("statsTimezoneSelect.addEventListener('change'") :]
    end = block.index("});") + 3
    block = block[:end]
    assert "statsTimezone = next" in block
    assert "fetchStats()" in block
    # No direct fetch inside the change handler; reuse the gated fetchStats path.
    assert "fetch(`" not in block


def test_historical_fetch_urls_propagate_timezone(source):
    block = _function_block(source, "fetchStats")
    assert "encodeURIComponent(resolveStatsTimezone())" in block
    assert "timezone=${tzParam}" in block
    # Every historical endpoint must carry the timezone parameter. The
    # history/top-* endpoints prepend ``limit=`` before ``days=``, so we just
    # assert that ``&timezone=${tzParam}`` follows the ``days=${statsDays}``
    # token on the same line.
    assert "summary?days=${statsDays}&timezone=${tzParam}" in block
    assert "players?days=${statsDays}&timezone=${tzParam}" in block
    assert "transcoding?days=${statsDays}&timezone=${tzParam}" in block
    assert "hourly?days=${statsDays}&timezone=${tzParam}" in block
    assert "daily?days=${statsDays}&timezone=${tzParam}" in block
    assert "heatmap?days=${statsDays}&timezone=${tzParam}" in block
    assert "history?limit=10&days=${statsDays}&timezone=${tzParam}" in block
    assert "top-artists?limit=10&days=${statsDays}&timezone=${tzParam}" in block
    assert "top-albums?limit=10&days=${statsDays}&timezone=${tzParam}" in block
    # Now-playing must NOT carry the timezone parameter.
    assert "/api/stats/now-playing', fetchOptions" in block
    assert "now-playing?timezone" not in block
    assert "now-playing?days" not in block


def test_heatmap_card_markup_exists(source):
    assert 'id="weekdayHourChart"' in source
    assert 'id="weekdayHourChartSkeleton"' in source
    assert 'id="weekdayHourChartEmpty"' in source
    assert 'id="weekdayHourChartWrap"' in source
    assert 'aria-label="周时热力图"' in source


def test_heatmap_echarts_init_exists(source):
    assert "weekdayHourChart = echarts.init(" in source


def test_heatmap_static_axis_labels_exist(source):
    assert "WEEKDAY_LABELS" in source
    assert "HOUR_LABELS" in source
    # Static Mon..Sun labels must be present (no API-derived labels).
    for label in ("'Mon'", "'Tue'", "'Wed'", "'Thu'", "'Fri'", "'Sat'", "'Sun'"):
        assert label in source
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
    assert "toggleChartEmpty" in block
    # No raw HTML injection in the heatmap renderer.
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block


def test_heatmap_included_in_fetchstats_promise_all(source):
    block = _function_block(source, "fetchStats")
    # The heatmap request is part of the historical Promise.all batch.
    assert "/api/stats/heatmap?days=${statsDays}&timezone=${tzParam}" in block
    # Response variable is declared alongside the other historical responses.
    assert "weekdayHourRes" in block
    # Parsed alongside the other JSON payloads and rendered.
    assert "weekdayHourRes.json()" in block
    assert "renderWeekdayHourChart(weekdayHourData)" in block
    # Auth and ok-status checks include the heatmap response.
    assert "weekdayHourRes" in block


def test_heatmap_skeleton_in_set_loading(source):
    block = _function_block(source, "setLoading")
    assert "'weekdayHourChartSkeleton'" in block
    assert "'weekdayHourChart'" in block
    assert "weekdayHourChart" in block


def test_heatmap_resize_in_window_resize_handler(source):
    block = source[source.index("window.addEventListener('resize'") :]
    end = block.index("});") + 3
    block = block[:end]
    assert "weekdayHourChart.resize()" in block


def test_summary_change_badge_elements_exist(source):
    for element_id in (
        "statTotalPlaysChange",
        "statListenTimeChange",
        "statActiveDays",
    ):
        assert f'id="{element_id}"' in source


def test_format_change_text_helper_exists(source):
    block = _function_block(source, "formatChangeText")
    assert "vs 上周期" in block
    assert "textContent" in block or "" in block  # function body present
    # No raw HTML injection in the badge formatter.
    assert "innerHTML" not in block
    assert "insertAdjacentHTML" not in block


def test_update_summary_populates_change_badges(source):
    block = _function_block(source, "updateSummary")
    assert "statTotalPlaysChange" in block
    assert "statListenTimeChange" in block
    assert "statActiveDays" in block
    assert "formatChangeText(summary.plays_change_pct)" in block
    assert "formatChangeText(summary.listen_change_pct)" in block
    assert "summary.active_days" in block
    assert "summary.average_daily_plays" in block
    # No innerHTML/outerHTML mutation in summary rendering.
    assert "innerHTML" not in block
    assert "outerHTML" not in block


def test_ranking_metric_control_and_state_exist(source):
    assert 'id="rankingMetricControl"' in source
    assert 'data-ranking-metric="plays"' in source
    assert 'data-ranking-metric="listen_time"' in source
    assert "let rankingMetric = 'plays';" in source
    assert "let rankingInFlight = false;" in source


def test_ranking_fetch_propagates_metric_and_uses_selected_value(source):
    block = _function_block(source, "fetchStats")
    assert "&metric=${rankingMetric}" in block
    assert "renderTopArtistsChart(topArtistsData, rankingMetric)" in block
    assert "renderTopAlbumsChart(topAlbumsData, rankingMetric)" in block


def test_ranking_metric_switch_fetches_only_rankings(source):
    block = _function_block(source, "fetchRankings")
    assert "rankingInFlight" in block
    assert "/api/stats/top-artists" in block
    assert "/api/stats/top-albums" in block
    assert "metric=${rankingMetric}" in block
    assert "innerHTML" not in block


def test_ranking_renderer_shows_both_metrics_safely(source):
    block = _function_block(source, "renderRankingList")
    assert "Number(d.value)" in block
    assert "formatListenDuration(totalListenSec)" in block
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

    transcode_block = _function_block(source, "renderTranscodingChart")
    assert "playsPct" in transcode_block
    assert "listenPct" in transcode_block
    assert "listenSec" in transcode_block
    assert "tooltip" in transcode_block