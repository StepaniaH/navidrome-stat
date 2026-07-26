"""Source-level checks for dashboard additions introduced alongside the
prioritized robustness/UX changes:

* the "正在播放" local elapsed ticker exists and only updates DOM text via
  ``textContent`` (no extra API calls, no innerHTML/insertAdjacentHTML),
* the daily trend time-range segmented control renders 7/30/90 buttons and
  uses ``/api/stats/daily?days=N``.

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


def test_daily_days_segmented_control_exists(source):
    assert 'id="dailyDaysControl"' in source
    for label in ("7 天", "30 天", "90 天"):
        assert label in source


def test_daily_days_buttons_carry_data_days(source):
    for n in (7, 30, 90):
        assert f'data-days="{n}"' in source


def test_daily_fetch_uses_days_param(source):
    block = _function_block(source, "fetchDaily")
    assert "/api/stats/daily?days=${dailyDays}" in block
    assert "dailyFetchInFlight" in block


def test_fetchstats_uses_daily_days(source):
    block = _function_block(source, "fetchStats")
    assert "/api/stats/daily?days=${dailyDays}" in block


def test_daily_button_click_updates_state_and_calls_fetch(source):
    block = source[source.index("document.querySelectorAll('.daily-days-btn')") :]
    end = block.index("setActiveDailyButton(dailyDays);")
    block = block[:end]
    assert "addEventListener('click'" in block
    assert "dailyDays = days" in block
    assert "fetchDaily()" in block


def test_daily_subtitle_updates_to_selected_range(source):
    block = _function_block(source, "setActiveDailyButton")
    assert "最近 ${days} 天每日播放次数" in block


def test_daily_chart_subtitle_has_id(source):
    assert 'id="dailyChartSubtitle"' in source