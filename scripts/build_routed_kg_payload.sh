#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
Usage: scripts/build_routed_kg_payload.sh RUN_ID [build_author_tables args...]

Rebuilds the routed KG tables, refreshes the author identity/authorship layer,
exports the private query-service runtime, exports the allowlisted compact
graph/dashboard/detail payloads used by the browser UI, and promotes the complete
release through the guarded publisher when explicitly requested.

Examples:
  scripts/build_routed_kg_payload.sh gemini3_flash_20260628_primary_extraction
  AUTHOR_CACHE_SEED=/path/to/openalex_author_cache.json \
    scripts/build_routed_kg_payload.sh gemini3_flash_20260628_primary_extraction --offline

Environment overrides:
  KG_DIR=/path/to/kg-run
  PAYLOAD_DIR=/path/to/graph-payload-run
  QUERY_DIR=/path/to/query-api-run
  EVIDENCE_RUN_ID=existing-run  # rebuild a new release from an existing evidence snapshot
  AUTHOR_CACHE_SEED=/path/to/cache  # optional override; EVIDENCE_RUN_ID caches are inherited automatically
  REVIEW_BASELINE_DIR=/path/to/reviewed-kg-run  # carry unchanged reviewed decisions before exports
  AUTHOR_AUDIT_DIR=/path/to/audit  # defaults to KG_DIR/author_identity_audit
  ACTIVATE_DEFAULT=1  # explicitly promote this run after the versioned build succeeds
  PUBLISH_QUERY_API_R2=1  # publish the promoted browser/API release and trigger the API deploy hook
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
QUERY_DIR="${QUERY_DIR:-"${ROOT_DIR}/data/processed/query_api_runs/${RUN_ID}"}"
AUTHOR_CACHE="${KG_DIR}/openalex_author_cache.json"
ACTIVATE_DEFAULT="${ACTIVATE_DEFAULT:-0}"
PUBLISH_QUERY_API_R2="${PUBLISH_QUERY_API_R2:-0}"
EVIDENCE_RUN_ID="${EVIDENCE_RUN_ID:-${RUN_ID}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OFFLINE_REQUESTED=0
RESOLVED_AUTHOR_CACHE_SEED="${AUTHOR_CACHE_SEED:-}"

for argument in "$@"; do
  if [[ "${argument}" == "--offline" ]]; then
    OFFLINE_REQUESTED=1
  fi
done

if [[ "${ACTIVATE_DEFAULT}" != "0" && "${ACTIVATE_DEFAULT}" != "1" ]]; then
  echo "ACTIVATE_DEFAULT must be 0 or 1" >&2
  exit 2
fi

if [[ "${PUBLISH_QUERY_API_R2}" != "0" && "${PUBLISH_QUERY_API_R2}" != "1" ]]; then
  echo "PUBLISH_QUERY_API_R2 must be 0 or 1" >&2
  exit 2
fi

if [[ "${PUBLISH_QUERY_API_R2}" == "1" && "${ACTIVATE_DEFAULT}" != "1" ]]; then
  echo "PUBLISH_QUERY_API_R2=1 requires ACTIVATE_DEFAULT=1" >&2
  exit 2
fi

# Carry-forward is intentionally append-only. Reject an active or baseline
# target before the expensive evidence build instead of discovering the unsafe
# target only after that build completes.
if [[ -n "${REVIEW_BASELINE_DIR:-}" ]]; then
  "${PYTHON_BIN}" - "${ROOT_DIR}" "${KG_DIR}" "${REVIEW_BASELINE_DIR}" <<'PY'
import json
import sys
from pathlib import Path

root, candidate, baseline = map(Path, sys.argv[1:])
pointer = json.loads((root / "data/processed/extraction/active_routed_run.json").read_text())
active = (root / pointer["kg_dir"]).resolve()
if candidate.resolve() in {active, baseline.resolve()}:
    raise SystemExit(
        "Refusing to rebuild review carry-forward into the baseline or active release; "
        "choose a new RUN_ID and set EVIDENCE_RUN_ID to the source snapshot."
    )
PY
fi

if [[ -n "${RESOLVED_AUTHOR_CACHE_SEED}" && ! -f "${RESOLVED_AUTHOR_CACHE_SEED}" ]]; then
  echo "AUTHOR_CACHE_SEED does not exist: ${RESOLVED_AUTHOR_CACHE_SEED}" >&2
  exit 2
fi

if [[ -z "${RESOLVED_AUTHOR_CACHE_SEED}" && "${EVIDENCE_RUN_ID}" != "${RUN_ID}" ]]; then
  SOURCE_AUTHOR_CACHE="${ROOT_DIR}/data/processed/kg_routed_runs/${EVIDENCE_RUN_ID}/openalex_author_cache.json"
  if [[ -f "${SOURCE_AUTHOR_CACHE}" ]]; then
    RESOLVED_AUTHOR_CACHE_SEED="${SOURCE_AUTHOR_CACHE}"
  fi
fi

if [[ "${OFFLINE_REQUESTED}" == "1" && ! -f "${AUTHOR_CACHE}" && -z "${RESOLVED_AUTHOR_CACHE_SEED}" ]]; then
  echo "Offline author build refused: ${AUTHOR_CACHE} does not exist." >&2
  echo "Set AUTHOR_CACHE_SEED=/path/to/openalex_author_cache.json, use EVIDENCE_RUN_ID with an existing cache, or omit --offline." >&2
  exit 2
fi

"${PYTHON_BIN}" "${ROOT_DIR}/pipeline/kg/build_evidence_tables.py" \
  --source-preset routed \
  --run-id "${RUN_ID}" \
  --evidence-run-id "${EVIDENCE_RUN_ID}" \
  --out-dir "${KG_DIR}"

if [[ -n "${REVIEW_BASELINE_DIR:-}" ]]; then
  "${PYTHON_BIN}" "${ROOT_DIR}/pipeline/validate/carry_forward_research_area_reviews.py" \
    --baseline-dir "${REVIEW_BASELINE_DIR}" \
    --candidate-dir "${KG_DIR}"
fi

if [[ ! -f "${AUTHOR_CACHE}" && -n "${RESOLVED_AUTHOR_CACHE_SEED}" ]]; then
  cp "${RESOLVED_AUTHOR_CACHE_SEED}" "${AUTHOR_CACHE}"
  echo "Seeded author cache from ${RESOLVED_AUTHOR_CACHE_SEED}"
fi

if [[ "${OFFLINE_REQUESTED}" == "1" && ! -f "${AUTHOR_CACHE}" ]]; then
  echo "Offline author build refused: ${AUTHOR_CACHE} does not exist." >&2
  echo "Set AUTHOR_CACHE_SEED=/path/to/openalex_author_cache.json, use EVIDENCE_RUN_ID with an existing cache, or omit --offline." >&2
  exit 2
fi

"${PYTHON_BIN}" "${ROOT_DIR}/pipeline/kg/build_author_tables.py" \
  --papers "${KG_DIR}/papers.parquet" \
  --out-dir "${KG_DIR}" \
  --cache "${AUTHOR_CACHE}" \
  "$@"

AUTHOR_AUDIT_DIR="${AUTHOR_AUDIT_DIR:-"${KG_DIR}/author_identity_audit"}"
AUTHOR_AUDIT_ARGS=(
  --kg-dir "${KG_DIR}"
  --out-dir "${AUTHOR_AUDIT_DIR}"
)
if [[ -n "${REVIEW_BASELINE_DIR:-}" ]]; then
  AUTHOR_AUDIT_ARGS+=(
    --baseline-dir "${REVIEW_BASELINE_DIR}"
    --fail-on-new-integrity-errors
  )
fi
"${PYTHON_BIN}" "${ROOT_DIR}/pipeline/validate/audit_author_identities.py" \
  "${AUTHOR_AUDIT_ARGS[@]}"

"${PYTHON_BIN}" "${ROOT_DIR}/pipeline/publish/export_query_api.py" \
  --kg-dir "${KG_DIR}" \
  --out-dir "${QUERY_DIR}" \
  --run-id "${RUN_ID}"

"${PYTHON_BIN}" "${ROOT_DIR}/pipeline/publish/export_evidence_payload.py" \
  --kg-dir "${KG_DIR}" \
  --out-dir "${PAYLOAD_DIR}"

if [[ "${ACTIVATE_DEFAULT}" == "1" ]]; then
  PROMOTION_ARGS=(--run-id "${RUN_ID}")
  if [[ "${EVIDENCE_RUN_ID}" != "${RUN_ID}" ]]; then
    EVIDENCE_RUN_DIR="${ROOT_DIR}/data/processed/extraction/routed_runs/${EVIDENCE_RUN_ID}"
    PROMOTION_ARGS+=(
      --outputs-jsonl "${EVIDENCE_RUN_DIR}/route_extraction_outputs.jsonl"
      --evidence-rows-json "${EVIDENCE_RUN_DIR}/routed_evidence_rows.json"
    )
    if [[ -f "${EVIDENCE_RUN_DIR}/source_update_manifest.json" ]]; then
      PROMOTION_ARGS+=(--source-update-manifest "${EVIDENCE_RUN_DIR}/source_update_manifest.json")
    fi
  fi
  "${PYTHON_BIN}" "${ROOT_DIR}/pipeline/publish/promote_routed_run.py" "${PROMOTION_ARGS[@]}"
fi

if [[ "${PUBLISH_QUERY_API_R2}" == "1" ]]; then
  "${PYTHON_BIN}" "${ROOT_DIR}/pipeline/publish/publish_browser_payload_r2.py" --run-id "${RUN_ID}"
  "${PYTHON_BIN}" "${ROOT_DIR}/pipeline/publish/publish_query_api_r2.py" --run-id "${RUN_ID}"
  "${PYTHON_BIN}" "${ROOT_DIR}/pipeline/publish/prune_release_history.py" \
    --remote \
    --local \
    --execute
fi
