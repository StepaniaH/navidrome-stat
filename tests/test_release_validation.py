"""Tests for strict release metadata validation."""

from scripts.validate_release import validation_errors


def test_release_validation_accepts_stable_and_prerelease_tags():
    assert validation_errors("v1.2.3", "1.2.3", "1.2.3", "- Released.") == []
    assert validation_errors(
        "v1.2.3-rc.1",
        "1.2.3-rc.1",
        "1.2.3-rc.1",
        "- Candidate.",
    ) == []


def test_release_validation_rejects_loose_tags_and_build_metadata():
    assert validation_errors("vnext", "1.2.3", "1.2.3", "- Notes.")
    assert validation_errors("v1.2.3+build.1", "1.2.3", "1.2.3", "- Notes.")


def test_release_validation_reports_version_and_changelog_mismatches():
    errors = validation_errors("v1.2.3", "1.2.2", "1.2.1", "")
    assert len(errors) == 3
    assert "src/version.py" in errors[0]
    assert "Dockerfile" in errors[1]
    assert "CHANGELOG.md" in errors[2]
