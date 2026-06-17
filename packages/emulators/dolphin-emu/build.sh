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

# On arm64 cross-compile the host LLVM (/usr/lib/llvm-19) is x86_64; linking it
# against aarch64 objects fails with "file in wrong format". Disable LLVM detection;
# dolphin falls back to the interpreter-based DSP without it.
_llvm_flag=()
[[ "${ARCH:-amd64}" == "arm64" ]] && _llvm_flag=(-DCMAKE_DISABLE_FIND_PACKAGE_LLVM=ON)

cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="/opt/hippos/qt/6.11/lib" \
    -DENABLE_QT=ON \
    -DENABLE_NOGUI=ON \
    -DENABLE_TESTS=OFF \
    -DUSE_SHARED_ENET=OFF \
    "${_llvm_flag[@]}"
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING} (version ${TAG})"
