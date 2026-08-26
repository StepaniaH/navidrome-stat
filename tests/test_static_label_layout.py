"""Source-level checks for the artist and album ranking lists."""

from pathlib import Path

import pytest

INDEX_HTML = Path(__file__).resolve().parent.parent / "src" / "static" / "index.html"
DASHBOARD_JS = Path(__file__).resolve().parent.parent / "src" / "static" / "dashboard.js"
DASHBOARD_CSS = Path(__file__).resolve().parent.parent / "src" / "static" / "dashboard.css"


@pytest.fixture(scope="module")
def source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (INDEX_HTML, DASHBOARD_JS, DASHBOARD_CSS)
    )


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


def test_render_ranking_list_uses_create_element_only(source):
    block = _function_block(source, "renderRankingList")
    assert "document.createElement" in block
    # No raw HTML string interpolation into the DOM container.
    assert "insertAdjacentHTML" not in block
    assert "outerHTML" not in block


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
def test_top_containers_have_list_role_and_aria_label(source, container_id, aria_label):
    line = next(
        line for line in source.splitlines()
        if f'id="{container_id}"' in line and "ranking-table" in line
    )
    assert 'role="list"' in line
    assert f'aria-label="{aria_label}"' in line


def test_top_containers_keep_skeleton_and_empty_states(source):
    for prefix in ("topArtistsChart", "topAlbumsChart"):
        assert f'id="{prefix}Skeleton"' in source
        assert f'id="{prefix}Empty"' in source
