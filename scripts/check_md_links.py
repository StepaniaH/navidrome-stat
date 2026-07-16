#!/usr/bin/env python3
from pathlib import Path
import re
import sys


def main() -> int:
    root = Path.cwd()
    missing = []
    pattern = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
    for document in sorted(root.rglob("*.md")):
        if ".git" in document.parts:
            continue
        text = document.read_text(encoding="utf-8")
        for target in pattern.findall(text):
            target = target.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            path = (document.parent / target).resolve()
            if not path.exists():
                missing.append(f"{document.relative_to(root)} -> {target}")
    if missing:
        print("Missing local Markdown links:")
        print("\n".join(missing))
        return 1
    print("All local Markdown links resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
