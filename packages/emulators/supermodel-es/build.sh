#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='supermodel-es'
REPO='https://github.com/rtissera/Supermodel'
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"

source "/work/packages/emulators/supermodel/supermodel-family.sh"

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} (default branch — no releases)"
    rm -rf "${SRC}"
    GIT_TERMINAL_PROMPT=0 git -c credential.helper= clone --depth=1 "${REPO}" "${SRC}"
fi

supermodel_build
supermodel_stage "$(git -C "${SRC}" rev-parse --short HEAD)"
