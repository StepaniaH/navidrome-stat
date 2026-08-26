#!/usr/bin/env python3
"""Print the CHANGELOG.md section body for a given version.

Usage: python3 scripts/release_notes.py 0.8.2
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parents[1] / "CHANGELOG.md"

SECTION_PATTERN = re.compile(r"^## \[(.+?)\]")
LINK_REFERENCE_PATTERN = re.compile(r"^\[[^\]]+\]:\s*\S+")


def parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = SECTION_PATTERN.match(line)
        if heading:
            current = heading.group(1)
            sections[current] = []
        elif LINK_REFERENCE_PATTERN.match(line):
            current = None
        elif current is not None:
            sections[current].append(line)
    return sections


def render_section(sections: dict[str, list[str]], version: str) -> str:
    return "\n".join(sections.get(version, [])).strip("\n")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(f"usage: {Path(sys.argv[0]).name} <version>", file=sys.stderr)
        return 1
    try:
        text = CHANGELOG_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"error: {CHANGELOG_PATH} not found", file=sys.stderr)
        return 1
    sections = parse_sections(text)
    if args[0] not in sections:
        available = ", ".join(sections) if sections else "(none)"
        print(
            f"error: no changelog section for '{args[0]}'. "
            f"Available versions: {available}",
            file=sys.stderr,
        )
        return 1
    print(render_section(sections, args[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
