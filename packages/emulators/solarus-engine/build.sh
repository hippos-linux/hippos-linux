#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='solarus-engine'
REPO='https://gitlab.com/solarus-games/solarus.git'
TAG="$(gitlab_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}"

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="\$ORIGIN/../lib" \
    -DSOLARUS_LIBRARY_INSTALL=ON \
    -DLUA_INCLUDE_DIR=/usr/include/luajit-2.1 \
    -DLUA_LIBRARY=/usr/lib/x86_64-linux-gnu/libluajit-5.1.so \
    -DLUAJIT_INCLUDE_DIR=/usr/include/luajit-2.1 \
    -DLUAJIT_LIBRARY=/usr/lib/x86_64-linux-gnu/libluajit-5.1.so

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

log "Installing"
cmake --install "${BUILD}"

if ! find "${STAGING}" -type f -perm /111 | grep -q .; then
    die "solarus-engine produced no executable artifact"
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
