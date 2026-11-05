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

# openMSX's configure has no --prefix; install locations are make variables
# (build/main.mk). The launcher points OPENMSX_SYSTEM_DATA at share/, so the
# path compiled into the binary doesn't matter.
INSTALL_VARS=(
    INSTALL_BINARY_DIR="${STAGING}/bin"
    INSTALL_SHARE_DIR="${STAGING}/share"
    INSTALL_DOC_DIR="${STAGING}/doc"
    SYMLINK_FOR_BINARY=false
)
(
    cd "${SRC}"
    ./configure
)
make -C "${SRC}" -j"$(nproc)" OPENMSX_TARGET_CPU=x86_64 "${INSTALL_VARS[@]}"
make -C "${SRC}" install "${INSTALL_VARS[@]}"
[[ -x "${STAGING}/bin/openmsx" ]] || { log "openmsx binary missing from ${STAGING}/bin after install"; exit 1; }
rm -rf "${STAGING}/doc"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
