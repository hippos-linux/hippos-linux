#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='dosbox-x'
REPO='https://github.com/joncampbell123/dosbox-x'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

mkdir -p "${STAGING}/bin"
cd "${SRC}"
if [[ -f autogen.sh ]]; then
    ./autogen.sh
fi
if [[ ! -f configure ]]; then
    autoreconf -fiv
fi
./configure --enable-sdl2 --prefix="${STAGING}"
make -j"$(nproc)"
make install

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
