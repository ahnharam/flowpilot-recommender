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

cd "${PROJECT_DIR}"

export APP_HOST_PORT="${APP_HOST_PORT:-8502}"
export API_HOST_PORT="${API_HOST_PORT:-8001}"

command -v git >/dev/null 2>&1 || {
  echo "[ERROR] git is required." >&2
  exit 1
}

as_root docker info >/dev/null
as_root docker compose version >/dev/null
as_root docker compose config >/dev/null

echo "[DEPLOY] Building FlowPilot"
as_root docker compose up --build --detach --remove-orphans

echo "[DEPLOY] Waiting for both services"
bash "${SCRIPT_DIR}/verify_deployment.sh"
