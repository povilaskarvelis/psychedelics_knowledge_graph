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

  if [[ -d "${src}" ]]; then
    mkdir -p "${dest}"
    cp -R "${src}/." "${dest}/"
  else
    mkdir -p "$(dirname "${dest}")"
    cp "${src}" "${dest}"
  fi
done < "${MANIFEST}"

find "${DIST_DIR}" -name ".DS_Store" -delete
python3 "${ROOT_DIR}/scripts/render_release_metadata.py" \
  --metadata "${ROOT_DIR}/release-metadata.json" \
  --site-dir "${DIST_DIR}"
python3 "${ROOT_DIR}/scripts/sanitize_public_json.py" \
  --manifest "${MANIFEST}" \
  --base-dir "${DIST_DIR}" \
  --root "${ROOT_DIR}"

if [[ "${missing}" -ne 0 ]]; then
  echo "Public site build failed because one or more required files were missing." >&2
  exit 1
fi

echo "Built static site in ${DIST_DIR}"
