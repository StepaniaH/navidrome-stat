"""Guard local sensitive data from source and container build contexts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _patterns(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_sensitive_local_data_is_excluded_from_git_and_docker_contexts():
    required = {".data/", "backups/", "coverart-cache/", "secret.key"}
    assert required <= _patterns(ROOT / ".gitignore")
    assert required <= _patterns(ROOT / ".dockerignore")
