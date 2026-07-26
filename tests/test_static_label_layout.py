"""Source-level checks for the top artist/album ranking list.

These tests assert static properties of the ranked bar-list implementation in
``src/static/index.html`` (formerly ECharts horizontal bar charts). They ensure
that:

* the two ECharts instances and their resize calls are gone,
* names are rendered as DOM rows with ``role="table"``/``role="row"`` and
  ``textContent`` assignment (no ``innerHTML`` XSS surface),
* bar widths are derived only from numeric counts and clamped to 0-100,
* the responsive fixed label column (42%) plus bar/value column layout is in
  place via a CSS grid,
* the purple (artists) and green (albums) gradients are preserved.

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
    # Skip the parameter list (track parens) so destructured object params
    # like `({ a, b })` do not confuse the brace matcher.
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


def test_top_charts_echarts_init_removed(source):
    assert "echarts.init(document.getElementById('topArtistsChart')" not in source
    assert "echarts.init(document.getElementById('topAlbumsChart')" not in source


def test_top_charts_resize_calls_removed(source):
    resize_block = source[source.index("window.addEventListener('resize'"):]
    assert "topArtistsChart.resize()" not in resize_block
    assert "topAlbumsChart.resize()" not in resize_block


def test_no_echarts_axis_config_for_top_rankings(source):
    for fn_name in ("renderTopArtistsChart", "renderTopAlbumsChart"):
        block = _function_block(source, fn_name)
        assert "xAxis" not in block
        assert "yAxis" not in block
        assert "axisLabel" not in block
        assert ".setOption(" not in block


def test_render_ranking_list_helper_exists(source):
    block = _function_block(source, "renderRankingList")
    assert "container.replaceChildren()" in block
    assert "Math.max(0, Math.min(100" in block
    assert "style.width = `${pct}%`" in block


def test_render_ranking_list_uses_textcontent_not_innerhtml(source):
    block = _function_block(source, "renderRankingList")
    assert "textContent" in block
    assert "innerHTML" not in block


def test_render_ranking_list_uses_create_element_only(source):
    block = _function_block(source, "renderRankingList")
    assert "document.createElement" in block
    # No raw HTML string interpolation into the DOM container.
    assert "insertAdjacentHTML" not in block
    assert "outerHTML" not in block


def test_render_ranking_list_sets_accessible_roles(source):
    block = _function_block(source, "renderRankingList")
    assert "'role', 'table'" in block
    assert "'role', 'row'" in block
    assert "'role', 'cell'" in block
    assert "'aria-label', ariaLabel" in block


@pytest.mark.parametrize("fn_name,label_key", [
    ("renderTopArtistsChart", "artist"),
    ("renderTopAlbumsChart", "album"),
])
def test_top_render_wrappers_delegate_to_helper(source, fn_name, label_key):
    block = _function_block(source, fn_name)
    assert "renderRankingList(" in block
    assert f"labelKey: '{label_key}'" in block


def test_ranking_row_grid_template_reserves_label_and_bar_columns(source):
    css = source[source.index(".ranking-row {") : source.index(".ranking-row +")]
    assert "grid-template-columns:" in css
    assert "minmax(0, 42%)" in css
    assert "minmax(0, 1fr)" in css
    assert "auto" in css


def test_ranking_table_is_not_locked_to_chart_height(source):
    css = source[source.index(".chart-container.ranking-table") : source.index(".pulse-dot")]
    assert "height: auto" in css
    assert "min-height" in css


def test_ranking_bar_gradients_preserved(source):
    artists_block = source[source.index(".ranking-bar-artists {") : source.index(".ranking-bar-albums {")]
    albums_block = source[source.index(".ranking-bar-albums {") : source.index(".ranking-count {")]
    assert "#7c5fd4" in artists_block and "#c4b5fd" in artists_block
    assert "#059669" in albums_block and "#34d399" in albums_block


@pytest.mark.parametrize("container_id,aria_label", [
    ("topArtistsChart", "热门艺人播放次数排行榜"),
    ("topAlbumsChart", "热门专辑播放次数排行榜"),
])
def test_top_containers_have_table_role_and_aria_label(source, container_id, aria_label):
    line = next(
        line for line in source.splitlines()
        if f'id="{container_id}"' in line and "ranking-table" in line
    )
    assert 'role="table"' in line
    assert f'aria-label="{aria_label}"' in line


def test_top_containers_keep_skeleton_and_empty_states(source):
    for prefix in ("topArtistsChart", "topAlbumsChart"):
        assert f'id="{prefix}Skeleton"' in source
        assert f'id="{prefix}Empty"' in source


def test_top_fetch_calls_preserved(source):
    assert "/api/stats/top-artists?limit=10" in source
    assert "/api/stats/top-albums?limit=10" in source