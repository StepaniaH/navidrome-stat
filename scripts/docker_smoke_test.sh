#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${SMOKE_IMAGE_NAME:-navidrome-stat-smoke:local}"
CONTAINER_NAME="${SMOKE_CONTAINER_NAME:-navidrome-stat-smoke}"
HOST_PORT="${SMOKE_HOST_PORT:-}"

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}

trap cleanup EXIT

cd "${ROOT_DIR}"

echo "Building image ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" .

cleanup

echo "Starting container ${CONTAINER_NAME}..."
if [[ -n "${HOST_PORT}" ]]; then
  PORT_ARGS=(-p "127.0.0.1:${HOST_PORT}:39421")
else
  PORT_ARGS=(-p "127.0.0.1::39421")
fi
docker run -d \
  --name "${CONTAINER_NAME}" \
  "${PORT_ARGS[@]}" \
  -e "NAVIDROME_URL=http://navidrome.example.invalid:4533" \
  -e "NAVIDROME_USER=smoke_user" \
  -e "NAVIDROME_PASS=smoke_pass" \
  -e "DATABASE_URL=/tmp/smoke.db" \
  "${IMAGE_NAME}"

if [[ -z "${HOST_PORT}" ]]; then
  HOST_PORT="$(docker port "${CONTAINER_NAME}" 39421/tcp | sed -E 's/.*:([0-9]+)$/\1/' | head -n 1)"
fi
if [[ ! "${HOST_PORT}" =~ ^[0-9]+$ ]]; then
  echo "Could not resolve the smoke-test host port." >&2
  exit 1
fi
BASE_URL="http://127.0.0.1:${HOST_PORT}"
echo "Smoke endpoint: ${BASE_URL}"

echo "Waiting for /health..."
for _ in $(seq 1 30); do
  if python3 -c "import urllib.request; urllib.request.urlopen('${BASE_URL}/health')"; then
    break
  fi
  sleep 1
done

python3 -c "
import json
import urllib.request

health = json.load(urllib.request.urlopen('${BASE_URL}/health'))
assert health == {'status': 'ok'}, health

ready = json.load(urllib.request.urlopen('${BASE_URL}/health/ready'))
assert ready['status'] in ('ready', 'degraded', 'not_ready'), ready
assert ready['checks']['database'] == 'ok', ready
print('Smoke test passed:', ready['status'])
"

echo "Stopping container ${CONTAINER_NAME}..."
