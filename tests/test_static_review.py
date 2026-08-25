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
