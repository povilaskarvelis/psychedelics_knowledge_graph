#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${DIST_DIR:-"${ROOT_DIR}/dist"}"
MANIFEST="${ROOT_DIR}/scripts/public_site_files.txt"

if [[ "${DIST_DIR}" != /* ]]; then
  DIST_DIR="$(pwd)/${DIST_DIR}"
fi

DIST_PARENT="$(dirname "${DIST_DIR}")"
DIST_BASENAME="$(basename "${DIST_DIR}")"
mkdir -p "${DIST_PARENT}"
DIST_DIR="$(cd "${DIST_PARENT}" && pwd -P)/${DIST_BASENAME}"

if [[ "${DIST_DIR}" == "${ROOT_DIR}/site" ]]; then
  echo "The site/ build output is retired. Use dist/ for the public site and local preview." >&2
  exit 1
fi

if [[ ! -f "${MANIFEST}" ]]; then
  echo "Missing public site manifest: ${MANIFEST}" >&2
  exit 1
fi

# Netlify builds from a clean checkout, so validate the committed public
# pointer, manifest, and browser payloads without requiring local corpus data.
python3 "${ROOT_DIR}/pipeline/publish/promote_routed_run.py" --check-public

rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

missing=0
while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
  item="${raw_line%%#*}"
  item="${item#"${item%%[![:space:]]*}"}"
  item="${item%"${item##*[![:space:]]}"}"

  if [[ -z "${item}" ]]; then
    continue
  fi

  src="${ROOT_DIR}/${item}"
  dest="${DIST_DIR}/${item}"

  if [[ ! -e "${src}" ]]; then
    echo "Missing public site file: ${item}" >&2
    missing=1
    continue
  fi

  if [[ "${item}" == "data/processed/graph_payload_runs" ]]; then
    active_config="${ROOT_DIR}/data/processed/graph_payload_active.json"
    if [[ ! -f "${active_config}" ]]; then
      echo "Missing active graph payload config: data/processed/graph_payload_active.json" >&2
      missing=1
      continue
    fi
    while IFS= read -r run_dir; do
      [[ -z "${run_dir}" ]] && continue
      run_src="${ROOT_DIR}/${run_dir}"
      run_dest="${DIST_DIR}/${run_dir}"
      if [[ ! -d "${run_src}" ]]; then
        echo "Missing active graph payload run: ${run_dir}" >&2
        missing=1
        continue
      fi
      mkdir -p "${run_dest}"
      cp -R "${run_src}/." "${run_dest}/"
    done < <(
      python3 - "${active_config}" <<'PY'
import json
import pathlib
import sys

config = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
references = [config.get("active_manifest", "")]
references.extend((config.get("active_graph_bootstraps") or {}).values())
references.extend((config.get("active_detail_bootstraps") or {}).values())
runs = set()
for reference in references:
    parts = pathlib.PurePosixPath(str(reference)).parts
    if "graph_payload_runs" not in parts:
        continue
    index = parts.index("graph_payload_runs")
    if len(parts) > index + 1:
        runs.add(pathlib.PurePosixPath(*parts[: index + 2]).as_posix())
for run in sorted(runs):
    print(run)
PY
    )
    continue
  fi

  if [[ -d "${src}" ]]; then
    mkdir -p "${dest}"
    cp -R "${src}/." "${dest}/"
  else
    mkdir -p "$(dirname "${dest}")"
    cp "${src}" "${dest}"
  fi
done < "${MANIFEST}"

find "${DIST_DIR}" -name ".DS_Store" -delete
python3 "${ROOT_DIR}/scripts/sanitize_public_json.py" \
  --manifest "${MANIFEST}" \
  --base-dir "${DIST_DIR}" \
  --root "${ROOT_DIR}"

if [[ "${missing}" -ne 0 ]]; then
  echo "Public site build failed because one or more required files were missing." >&2
  exit 1
fi

echo "Built static site in ${DIST_DIR}"
