#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"
source "/work/build/qt611-env.sh"

NAME='dolphin-emu'
REPO='https://github.com/dolphin-emu/dolphin'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

mkdir -p "${BUILD}" "${STAGING}/bin"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="/opt/hippos/qt/6.11/lib" \
    -DENABLE_QT=ON \
    -DENABLE_NOGUI=ON \
    -DENABLE_TESTS=OFF \
    -DUSE_SHARED_ENET=OFF
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING} (version ${TAG})"
