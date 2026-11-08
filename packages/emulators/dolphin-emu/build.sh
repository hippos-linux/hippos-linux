#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"
source "/work/build/qt-env.sh"

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

# A stale CMakeCache.txt reuses cached *_DIR values from whatever prefix
# resolved them last run instead of re-searching CMAKE_PREFIX_PATH/deps —
# always start clean.
rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

# LLVM only provides the debugger's disassembler. The build image's newest
# LLVM (21) isn't in the runtime OS, and on arm64 cross builds the host LLVM is
# the wrong architecture, so leave it out.
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${EMULATOR_RUNTIME_ROOT}/${NAME}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="${QT_RPATH}" \
    -DENABLE_QT=ON \
    -DENABLE_NOGUI=ON \
    -DENABLE_TESTS=OFF \
    -DUSE_SHARED_ENET=OFF \
    -DCMAKE_DISABLE_FIND_PACKAGE_LLVM=ON
cmake --build "${BUILD}" -j"$(nproc)"
install_staged "${NAME}" "${STAGING}" "${BUILD}/destdir" cmake --install "${BUILD}"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING} (version ${TAG})"
