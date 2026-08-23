#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Python 3.11 is required; set PYTHON_BIN to its executable." >&2
    exit 1
fi

PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PYTHON_VERSION}" != "3.11" ]]; then
    echo "Python 3.11 is required; ${PYTHON_BIN} reports ${PYTHON_VERSION}." >&2
    exit 1
fi

VENV="$(mktemp -d "${TMPDIR:-/tmp}/navidrome-stat-lock.XXXXXX")"
LOCK_TMP="$(mktemp "${ROOT}/.requirements.lock.XXXXXX")"

cleanup() {
    rm -rf "${VENV}"
    if [[ -n "${LOCK_TMP:-}" ]]; then
        rm -f "${LOCK_TMP}"
    fi
}
trap cleanup EXIT

"${PYTHON_BIN}" -m venv "${VENV}"
"${VENV}/bin/python" -m pip install -q --upgrade pip
"${VENV}/bin/python" -m pip install -q -r "${ROOT}/requirements.txt"
"${VENV}/bin/python" -m pip check
{
    echo "# Auto-generated runtime lock for reproducible installs (Python 3.11)."
    echo "# Refresh: scripts/refresh_requirements_lock.sh (requires Python 3.11)."
    "${VENV}/bin/python" -m pip freeze --all \
        | LC_ALL=C sort \
        | grep -Ev '^(pip|setuptools|wheel)=='
} > "${LOCK_TMP}"

if [[ ! -s "${LOCK_TMP}" ]]; then
    echo "Refusing to replace requirements.lock with an empty file." >&2
    exit 1
fi

chmod 0644 "${LOCK_TMP}"
mv "${LOCK_TMP}" "${ROOT}/requirements.lock"
LOCK_TMP=""

echo "Updated ${ROOT}/requirements.lock"
