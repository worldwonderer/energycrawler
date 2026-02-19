#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/webui-src/dist"
DST_DIR="${ROOT_DIR}/api/webui"

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "webui build output not found: ${SRC_DIR}"
  echo "Build frontend first, then rerun this script."
  exit 1
fi

rm -rf "${DST_DIR}"
mkdir -p "${DST_DIR}"
cp -R "${SRC_DIR}/." "${DST_DIR}/"

echo "Synced webui assets:"
echo "  from ${SRC_DIR}"
echo "  to   ${DST_DIR}"
