#!/usr/bin/env python3
"""Validate a release tag against source defaults and the changelog."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.release_notes import parse_sections, render_section  # noqa: E402

VERSION_PATH = PROJECT_ROOT / "src" / "version.py"
DOCKERFILE_PATH = PROJECT_ROOT / "Dockerfile"
CHANGELOG_PATH = PROJECT_ROOT / "CHANGELOG.md"

PRERELEASE_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER_TAG_PATTERN = re.compile(
    rf"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    rf"(?:-{PRERELEASE_IDENTIFIER}(?:\.{PRERELEASE_IDENTIFIER})*)?$"
)
APP_VERSION_PATTERN = re.compile(
    r'APP_VERSION\s*=\s*os\.getenv\("APP_VERSION",\s*"([^"]+)"\)'
)
DOCKER_VERSION_PATTERN = re.compile(r"^ARG APP_VERSION=([^\s]+)$", re.MULTILINE)


def validation_errors(
    tag: str,
    app_version: str,
    docker_version: str,
    changelog_body: str,
) -> list[str]:
    if not SEMVER_TAG_PATTERN.fullmatch(tag):
        return [
            "tag must be strict SemVer such as v1.2.3 or v1.2.3-rc.1 "
            "(build metadata is not supported in Docker tags)"
        ]

    version = tag[1:]
    errors = []
    if app_version != version:
        errors.append(
            f"src/version.py defaults to {app_version}, but the tag is {version}"
        )
    if docker_version != version:
        errors.append(
            f"Dockerfile defaults to {docker_version}, but the tag is {version}"
        )
    if not changelog_body.strip():
        errors.append(f"CHANGELOG.md has no release notes for {version}")
    return errors


def _match_version(path: Path, pattern: re.Pattern[str], label: str) -> str:
    match = pattern.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"could not read {label} from {path.relative_to(PROJECT_ROOT)}")
    return match.group(1)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(f"usage: {Path(sys.argv[0]).name} <vMAJOR.MINOR.PATCH>", file=sys.stderr)
        return 1

    try:
        app_version = _match_version(VERSION_PATH, APP_VERSION_PATTERN, "app version")
        docker_version = _match_version(
            DOCKERFILE_PATH,
            DOCKER_VERSION_PATTERN,
            "Docker build version",
        )
        sections = parse_sections(CHANGELOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    tag = args[0]
    version = tag[1:] if tag.startswith("v") else tag
    errors = validation_errors(
        tag,
        app_version,
        docker_version,
        render_section(sections, version),
    )
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"release metadata is consistent for {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
