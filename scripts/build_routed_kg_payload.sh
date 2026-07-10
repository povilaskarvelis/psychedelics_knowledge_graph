#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
Usage: scripts/build_routed_kg_payload.sh RUN_ID [build_author_tables args...]

Rebuilds the routed KG tables, refreshes the author identity/authorship layer,
then exports the compact graph/detail payloads used by the browser UI.

Examples:
  scripts/build_routed_kg_payload.sh gemini3_flash_20260628_primary_extraction
  scripts/build_routed_kg_payload.sh gemini3_flash_20260628_primary_extraction --offline

Environment overrides:
  KG_DIR=/path/to/kg-run
  PAYLOAD_DIR=/path/to/graph-payload-run
  ACTIVATE_DEFAULT=0  # skip rewriting data/processed/graph_payload_active.json
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

RUN_ID="${1:-}"
if [[ -z "${RUN_ID}" ]]; then
  usage
  exit 2
fi
shift

KG_DIR="${KG_DIR:-"${ROOT_DIR}/data/processed/kg_routed_runs/${RUN_ID}"}"
PAYLOAD_DIR="${PAYLOAD_DIR:-"${ROOT_DIR}/data/processed/graph_payload_runs/${RUN_ID}"}"

python3 "${ROOT_DIR}/pipeline/kg/build_evidence_tables.py" \
  --source-preset routed \
  --run-id "${RUN_ID}" \
  --out-dir "${KG_DIR}"

python3 "${ROOT_DIR}/pipeline/kg/build_author_tables.py" \
  --papers "${KG_DIR}/papers.parquet" \
  --out-dir "${KG_DIR}" \
  --cache "${KG_DIR}/openalex_author_cache.json" \
  "$@"

export_args=(
  --kg-dir "${KG_DIR}"
  --out-dir "${PAYLOAD_DIR}"
)
if [[ "${ACTIVATE_DEFAULT:-1}" != "0" ]]; then
  export_args+=(--activate-default)
fi

python3 "${ROOT_DIR}/pipeline/publish/export_evidence_payload.py" "${export_args[@]}"
