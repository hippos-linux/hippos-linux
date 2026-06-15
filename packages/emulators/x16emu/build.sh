#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='x16emu'
REPO='https://github.com/X16Community/x16-emulator'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ "${ARCH:-amd64}" == "arm64" ]]; then
    log "SKIP: x16emu Makefile hardcodes /usr/include/x86_64-linux-gnu/SDL2; no arm64 support"
    exit 0
fi

clone_source "${REPO}" "${TAG}" "${SRC}"

mkdir -p "${STAGING}/bin"
make -C "${SRC}" -j"$(nproc)"
cp "${SRC}/x16emu" "${STAGING}/bin/"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
