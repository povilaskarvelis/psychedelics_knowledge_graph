#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
Usage: scripts/build_routed_kg_payload.sh RUN_ID [build_author_tables args...]

Rebuilds the routed KG tables, refreshes the author identity/authorship layer,
exports the compact graph/detail payloads used by the browser UI, and refreshes
the Methods PRISMA flow and full bibliography when the run is activated.

Examples:
  scripts/build_routed_kg_payload.sh gemini3_flash_20260628_primary_extraction
  scripts/build_routed_kg_payload.sh gemini3_flash_20260628_primary_extraction --offline

Environment overrides:
  KG_DIR=/path/to/kg-run
  PAYLOAD_DIR=/path/to/graph-payload-run
  METHODS_OUT_DIR=/path/to/methods-output
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
METHODS_OUT_DIR="${METHODS_OUT_DIR:-"${ROOT_DIR}/data/kg"}"
AUTHOR_CACHE="${KG_DIR}/openalex_author_cache.json"

python3 "${ROOT_DIR}/pipeline/kg/build_evidence_tables.py" \
  --source-preset routed \
  --run-id "${RUN_ID}" \
  --out-dir "${KG_DIR}"

if [[ ! -f "${AUTHOR_CACHE}" && -n "${AUTHOR_CACHE_SEED:-}" && -f "${AUTHOR_CACHE_SEED}" ]]; then
  cp "${AUTHOR_CACHE_SEED}" "${AUTHOR_CACHE}"
fi

python3 "${ROOT_DIR}/pipeline/kg/build_author_tables.py" \
  --papers "${KG_DIR}/papers.parquet" \
  --out-dir "${KG_DIR}" \
  --cache "${AUTHOR_CACHE}" \
  "$@"

export_args=(
  --kg-dir "${KG_DIR}"
  --out-dir "${PAYLOAD_DIR}"
)
if [[ "${ACTIVATE_DEFAULT:-1}" != "0" ]]; then
  export_args+=(--activate-default)
  METHODS_STAGE="$(mktemp -d "${TMPDIR:-/tmp}/psychkg-methods.XXXXXX")"
  trap 'rm -rf "${METHODS_STAGE}"' EXIT
  python3 "${ROOT_DIR}/pipeline/kg/build_methods_flow.py" \
    --kg-dir "${KG_DIR}" \
    --out-dir "${METHODS_STAGE}"
fi

python3 "${ROOT_DIR}/pipeline/publish/export_evidence_payload.py" "${export_args[@]}"

if [[ "${ACTIVATE_DEFAULT:-1}" != "0" ]]; then
  for relative_path in \
    schema/methods_flow.schema.json \
    views/pipeline_status_graph.json \
    views/methods_bibliography.json \
    manifests/build_manifest.json
  do
    mkdir -p "${METHODS_OUT_DIR}/$(dirname "${relative_path}")"
    mv "${METHODS_STAGE}/${relative_path}" "${METHODS_OUT_DIR}/${relative_path}"
  done
  rm -rf "${METHODS_STAGE}"
  trap - EXIT
fi
