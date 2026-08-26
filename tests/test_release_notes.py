"""Tests for the release notes extractor in scripts/release_notes.py."""

from __future__ import annotations

import scripts.release_notes as release_notes

SAMPLE_CHANGELOG = """\
# Changelog

All notable user-facing changes are documented in this file.

## [Unreleased]

## [1.0.0] - 2026-01-01

### Added

- First feature.
- Second feature.

### Fixed

- A fix.

## [0.9.0] - 2025-12-31

- Older entry.

[1.0.0]: https://example.com/compare/v0.9.0...v1.0.0
[0.9.0]: https://example.com/tree/v0.9.0
"""

EXPECTED_BODY = (
    "### Added\n"
    "\n"
    "- First feature.\n"
    "- Second feature.\n"
    "\n"
    "### Fixed\n"
    "\n"
    "- A fix."
)


def write_sample_changelog(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE_CHANGELOG, encoding="utf-8")
    return changelog


def test_render_section_returns_body_between_headings():
    sections = release_notes.parse_sections(SAMPLE_CHANGELOG)
    assert release_notes.render_section(sections, "1.0.0") == EXPECTED_BODY


def test_unreleased_section_renders_empty_body():
    sections = release_notes.parse_sections(SAMPLE_CHANGELOG)
    assert release_notes.render_section(sections, "Unreleased") == ""


def test_link_references_excluded_from_final_section():
    sections = release_notes.parse_sections(SAMPLE_CHANGELOG)
    body = release_notes.render_section(sections, "0.9.0")
    assert body == "- Older entry."
    assert "https://example.com" not in body


def test_main_lists_available_versions_when_version_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(release_notes, "CHANGELOG_PATH", write_sample_changelog(tmp_path))
    assert release_notes.main(["9.9.9"]) == 1
    err = capsys.readouterr().err
    assert "no changelog section for '9.9.9'" in err
    assert "Unreleased, 1.0.0, 0.9.0" in err


def test_main_prints_requested_section_body(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(release_notes, "CHANGELOG_PATH", write_sample_changelog(tmp_path))
    assert release_notes.main(["1.0.0"]) == 0
    assert capsys.readouterr().out == EXPECTED_BODY + "\n"
