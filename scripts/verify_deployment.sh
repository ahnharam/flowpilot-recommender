#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

as_root() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

fail() {
  echo "[ERROR] $*" >&2
  exit 1
}

cd "${PROJECT_DIR}"

export APP_HOST_PORT="${APP_HOST_PORT:-8502}"
export API_HOST_PORT="${API_HOST_PORT:-8001}"

as_root docker compose version >/dev/null || fail "Docker Compose is unavailable."

echo "[VERIFY] Compose services"
as_root docker compose ps

for service in api web; do
  container_id="$(as_root docker compose ps --quiet "${service}")"
  [[ -n "${container_id}" ]] || fail "${service} container is not running."

  health="unknown"
  for _attempt in {1..30}; do
    health="$(as_root docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "${container_id}")"
    [[ "${health}" == "healthy" ]] && break
    [[ "${health}" == "unhealthy" ]] && {
      as_root docker logs --tail 80 "${container_id}" >&2 || true
      fail "${service} container is unhealthy."
    }
    sleep 2
  done
  [[ "${health}" == "healthy" ]] || fail "${service} did not become healthy."

  restart_policy="$(as_root docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "${container_id}")"
  [[ "${restart_policy}" == "always" ]] || fail "${service} restart policy is ${restart_policy:-missing}."

  container_user="$(as_root docker inspect --format '{{.Config.User}}' "${container_id}")"
  case "${container_user}" in
    ""|0|0:0|root|root:root) fail "${service} is running as root." ;;
  esac

  echo "[VERIFY] ${service}: healthy · restart=${restart_policy} · user=${container_user}"
done

echo "[VERIFY] FastAPI health"
curl --fail --silent --show-error --max-time 8 \
  "http://127.0.0.1:${API_HOST_PORT}/health"
echo

echo "[VERIFY] Streamlit health"
curl --fail --silent --show-error --max-time 8 \
  "http://127.0.0.1:${APP_HOST_PORT}/_stcore/health"
echo

echo "[VERIFY] Streamlit container → FastAPI recommendation round trip"
recommendation="$(
  as_root docker compose exec --no-TTY web python -c '
import json
import os
import requests

payload = {
    "goal": "finish final deployment verification",
    "available_minutes": 75,
    "energy_level": 4,
    "environment": "cafe",
    "task_type": "coding",
    "interruption_level": "medium",
    "preferred_style": "structured",
}
endpoint = os.environ["API_URL"].rstrip("/") + "/api/v1/recommend"
response = requests.post(endpoint, json=payload, timeout=15)
response.raise_for_status()
print(json.dumps(response.json(), ensure_ascii=False))
'
)"

grep --quiet '"recommendation"' <<<"${recommendation}" \
  || fail "Recommendation JSON is missing the recommendation field."
grep --quiet '"timeline"' <<<"${recommendation}" \
  || fail "Recommendation JSON is missing the timeline field."

echo "${recommendation}"
echo
echo "[VERIFY] PASS · web container → FastAPI JSON contract and both services are ready"
