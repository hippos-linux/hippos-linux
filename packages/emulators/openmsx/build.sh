#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='openmsx'
REPO='https://github.com/openMSX/openMSX'
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
(
    cd "${SRC}"
    ./configure --prefix="${STAGING}"
)
make -C "${SRC}" -j"$(nproc)" OPENMSX_TARGET_CPU=x86_64
make -C "${SRC}" install

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
