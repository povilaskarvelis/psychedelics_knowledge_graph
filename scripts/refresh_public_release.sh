#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
Usage: scripts/refresh_public_release.sh [RUN_ID]

Regenerates the browser graph and public API from an already-built KG run,
binds them to one new public release ID, validates the static site, and
publishes both browser and API releases to R2. RUN_ID defaults to the current
graph run.

Use this for public-export, author-identity, API, or browser-payload changes
that do not change the underlying evidence decisions. For a new evidence run,
use scripts/build_routed_kg_payload.sh with ACTIVATE_DEFAULT=1 and
PUBLISH_QUERY_API_R2=1 instead.

Environment:
  ENV_FILE=/path/to/.env       Defaults to the repository .env file.
  NO_R2_PUBLISH=1              Build and validate locally without changing R2.
  WRITE_LEGACY_R2_ALIAS=1      Also update query-api/active.json during the
                               one-time catalogue-v2 migration.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

RUN_ID="${1:-}"
if [[ -z "${RUN_ID}" ]]; then
  RUN_ID="$(python3 - "${ROOT_DIR}/data/processed/graph_payload_active.json" <<'PY'
import json
import pathlib
import sys

pointer = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(str(pointer.get("run_id") or "").strip())
PY
)"
fi
if [[ -z "${RUN_ID}" ]]; then
  echo "Could not determine a run ID." >&2
  exit 2
fi

KG_DIR="${KG_DIR:-${ROOT_DIR}/data/processed/kg_routed_runs/${RUN_ID}}"
PAYLOAD_DIR="${PAYLOAD_DIR:-${ROOT_DIR}/data/processed/graph_payload_runs/${RUN_ID}}"
QUERY_DIR="${QUERY_DIR:-${ROOT_DIR}/data/processed/query_api_runs/${RUN_ID}}"
NO_R2_PUBLISH="${NO_R2_PUBLISH:-0}"
WRITE_LEGACY_R2_ALIAS="${WRITE_LEGACY_R2_ALIAS:-0}"

for name in NO_R2_PUBLISH WRITE_LEGACY_R2_ALIAS; do
  value="${!name}"
  if [[ "${value}" != "0" && "${value}" != "1" ]]; then
    echo "${name} must be 0 or 1" >&2
    exit 2
  fi
done

python3 "${ROOT_DIR}/pipeline/publish/export_query_api.py" \
  --kg-dir "${KG_DIR}" \
  --out-dir "${QUERY_DIR}" \
  --run-id "${RUN_ID}"

python3 "${ROOT_DIR}/pipeline/publish/export_evidence_payload.py" \
  --kg-dir "${KG_DIR}" \
  --out-dir "${PAYLOAD_DIR}"

python3 "${ROOT_DIR}/pipeline/publish/promote_routed_run.py" \
  --refresh-public \
  --run-id "${RUN_ID}"

if [[ "${NO_R2_PUBLISH}" == "0" ]]; then
  python3 "${ROOT_DIR}/pipeline/publish/publish_browser_payload_r2.py" --run-id "${RUN_ID}"
  publish_args=(--run-id "${RUN_ID}")
  if [[ "${WRITE_LEGACY_R2_ALIAS}" == "1" ]]; then
    publish_args+=(--write-legacy-active-alias)
  fi
  python3 "${ROOT_DIR}/pipeline/publish/publish_query_api_r2.py" "${publish_args[@]}"
else
  echo "Skipped browser and API R2 publication because NO_R2_PUBLISH=1"
fi

python3 "${ROOT_DIR}/pipeline/publish/promote_routed_run.py" --check-public
echo "Public release is synchronized and ready to commit."
