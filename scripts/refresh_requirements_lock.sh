#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${ROOT}/.venv-lock-tmp"

rm -rf "${VENV}"
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install -q --upgrade pip
"${VENV}/bin/pip" install -q -r "${ROOT}/requirements.txt"
"${VENV}/bin/pip" freeze | LC_ALL=C sort | rg -v '^(pip|setuptools|wheel)=='> "${ROOT}/requirements.lock"
rm -rf "${VENV}"

echo "Updated ${ROOT}/requirements.lock"
