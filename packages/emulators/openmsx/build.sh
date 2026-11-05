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
# (build/main.mk), and INSTALL_SHARE_DIR is compiled in as the system data dir.
RUNTIME_PREFIX="${EMULATOR_RUNTIME_ROOT}/${NAME}"
INSTALL_VARS=(
    INSTALL_BINARY_DIR="${RUNTIME_PREFIX}/bin"
    INSTALL_SHARE_DIR="${RUNTIME_PREFIX}/share"
    INSTALL_DOC_DIR="${RUNTIME_PREFIX}/doc"
    SYMLINK_FOR_BINARY=false
)
# derived/ holds build-info.hh with the install paths, which make doesn't
# regenerate when they change.
rm -rf "${SRC}/derived"
(
    cd "${SRC}"
    ./configure
    make -j"$(nproc)" OPENMSX_TARGET_CPU=x86_64 "${INSTALL_VARS[@]}"
    install_staged "${NAME}" "${STAGING}" "${BUILD}/destdir" make install "${INSTALL_VARS[@]}"
)
[[ -x "${STAGING}/bin/openmsx" ]] || { log "openmsx binary missing from ${STAGING}/bin after install"; exit 1; }
rm -rf "${STAGING}/doc"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
