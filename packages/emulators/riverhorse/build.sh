#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='riverhorse'
REPO='https://github.com/thenotoriousfox/riverhorse.git'
TAG="${RIVERHORSE_TAG:-$(github_latest_tag "${REPO}")}"

WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

log "Building ${TAG}"
clone_source "${REPO}" "${TAG}" "${SRC}"

BUILT_BIN='riverhorse'
STAGED_BIN='riverhorse'
VERSION="${TAG}"
DOC_FILES=(LICENSE NOTICE.md)
source "/work/packages/emulators/duckstation/duckstation-family.sh"
