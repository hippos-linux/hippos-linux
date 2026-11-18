#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='supermodel-legacy'
REPO='https://github.com/trzy/Supermodel'
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"

source "/work/packages/emulators/supermodel/supermodel-family.sh"

TAG="$(github_latest_tag "${REPO}" 2>/dev/null || true)"
if [[ -z "${TAG}" ]]; then
    log "No releases found for ${REPO}; skipping"
    exit 0
fi

clone_source "${REPO}" "${TAG}" "${SRC}"

supermodel_build
supermodel_stage "${TAG}"
