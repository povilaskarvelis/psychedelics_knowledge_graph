#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-}"
PORT="${PORT:-8011}"
BIND="${BIND:-127.0.0.1}"
RUN_ID="${RUN_ID:-}"

if [[ "${MODE}" != "public" && "${MODE}" != "local" ]]; then
  echo "Usage: scripts/preview_site.sh [public|local]" >&2
  echo "Optional environment: PORT=8011 RUN_ID=<generated-run-id>" >&2
  echo "The preview mode is required; there is no implicit release source." >&2
  exit 2
fi

bash "${ROOT_DIR}/scripts/build_site.sh"

args=(
  "${ROOT_DIR}/scripts/serve_site.py"
  --mode "${MODE}"
  --directory "${ROOT_DIR}/dist"
  --bind "${BIND}"
  --port "${PORT}"
)
if [[ -n "${RUN_ID}" ]]; then
  args+=(--run-id "${RUN_ID}")
fi

exec python3 "${args[@]}"
