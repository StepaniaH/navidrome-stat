"""Source-level checks for the Year in Review page."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW_HTML = ROOT / "src" / "static" / "review.html"
REVIEW_JS = ROOT / "src" / "static" / "js" / "review.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_review_loads_shared_theme_assets():
    html = _read(REVIEW_HTML)
    assert '<link rel="stylesheet" href="/static/themes.css">' in html
    assert '<script type="module" src="/static/theme-bootstrap.js"></script>' in html


def test_year_selector_uses_custom_listbox_not_native_select():
    assert "<select" not in _read(REVIEW_HTML)
    assert 'id="reviewYearMenu"' in _read(REVIEW_HTML)
    assert "createListbox" in _read(REVIEW_JS)


def test_review_charts_prevent_axis_label_overlap():
    js = _read(REVIEW_JS)
    assert "hideOverlap: true" in js
    assert "categoryInterval" in js
    assert "containLabel: true" in js

def test_review_chart_heights_increased():
    css = _read(ROOT / "src" / "static" / "dashboard.css")
    assert ".review-chart { width: 100%; height: 260px; }" in css
    assert ".review-chart-tall { height: 300px; }" in css


def test_review_covers_use_per_item_source_with_letter_fallback():
    js = _read(REVIEW_JS)
    assert "entry.source_id || sourceId" in js
    assert "review-top-cover-fallback" in js


def test_review_charts_resize_after_render():
    js = _read(REVIEW_JS)
    assert "resizeCharts()" in js


def test_review_charts_rerender_when_the_resolved_theme_changes():
    js = _read(REVIEW_JS)
    assert "THEME_CHANGE_EVENT" in js
    assert "window.addEventListener(THEME_CHANGE_EVENT" in js
    theme_change = js[js.index("window.addEventListener(THEME_CHANGE_EVENT") :]
    assert "renderCharts(lastReview)" in theme_change


def test_review_distribution_charts_support_metric_toggle():
    js = _read(REVIEW_JS)
    html = _read(ROOT / "src" / "static" / "review.html")
    assert 'id="reviewMetricControl"' in html
    assert 'data-review-metric="plays"' in html
    assert 'data-review-metric="listen_time"' in html
    assert "function setReviewMetric" in js
    assert "metricValue(entry)" in js
    assert "entry.total_listen_sec" in js
    toggle = js[js.index("function setReviewMetric") :]
    assert "aria-pressed" in toggle
    assert "renderCharts(lastReview)" in js
