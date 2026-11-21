#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='riverhorse'
REPO="${RIVERHORSE_REPO:-https://github.com/thenotoriousfox/riverhorse.git}"
REF="${RIVERHORSE_REF:-main}"
SHA="${RIVERHORSE_SHA:-7fb084fd91d3063a11f77606adf51b3c534bb588}"

WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ -d "${SRC}/.git" && "$(git -C "${SRC}" rev-parse HEAD 2>/dev/null)" != "${SHA}" ]]; then
    rm -rf "${SRC}"
fi
if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${SHA:0:12}"
    git clone --depth=1 --branch "${REF}" "${REPO}" "${SRC}"
    if [[ "$(git -C "${SRC}" rev-parse HEAD)" != "${SHA}" ]]; then
        git -C "${SRC}" fetch --depth=1 origin "${SHA}"
        git -C "${SRC}" checkout --quiet "${SHA}"
    fi
fi

BUILT_BIN='riverhorse'
STAGED_BIN='riverhorse'
VERSION="${SHA:0:12}"
DOC_FILES=(LICENSE NOTICE.md)
source "/work/packages/emulators/duckstation/duckstation-family.sh"
