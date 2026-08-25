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
