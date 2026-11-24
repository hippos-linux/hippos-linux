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

PATCH_DIR="${REPO_ROOT}/packages/emulators/${NAME}"
for patch in 001-netplay-join-option.patch 002-netplay-host-option.patch; do
    if git -C "${SRC}" apply --reverse --check "${PATCH_DIR}/${patch}" >/dev/null 2>&1; then
        log "Patch already applied: ${patch}"
    else
        git -C "${SRC}" apply "${PATCH_DIR}/${patch}"
    fi
done

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

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
