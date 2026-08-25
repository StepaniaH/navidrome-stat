"""Brand icon geometry must match the reference artwork spec."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON_FILES = [
    ROOT / "assets" / "icon.svg",
    ROOT / "assets" / "icon-dark.svg",
    ROOT / "src" / "static" / "favicon.svg",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_ellipse_note_head_anywhere():
    for path in ICON_FILES:
        assert "<ellipse" not in _read(path), path


def test_note_head_is_circle_at_specified_center():
    for path in ICON_FILES:
        assert '<circle cx="59" cy="71" r="8"' in _read(path), path


def test_sound_arcs_use_corrected_radii():
    for path in ICON_FILES:
        text = _read(path)
        for radius in ("13.5", "20", "26.5"):
            assert f"A {radius} {radius} 0 0 0" in text, path


def test_header_svg_matches_shared_geometry():
    html = _read(ROOT / "src" / "static" / "index.html")
    assert '<circle cx="59" cy="71" r="8"' in html
    assert "brandWave" in html
    assert "<ellipse" not in html
