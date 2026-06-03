#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='shadps4'
REPO='https://github.com/shadps4-emu/shadPS4.git'
TAG="$(github_latest_tag "${REPO}")"

WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

source "/work/build/qt611-env.sh"

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_EXE_LINKER_FLAGS_INIT="-fuse-ld=lld -lSPIRV-Tools -lSPIRV-Tools-opt" \
    -DCMAKE_MODULE_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_SHARED_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_PREFIX_PATH="${QT_ROOT}" \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="/opt/hippos/qt/6.11/lib" \
    -DENABLE_QT_GUI=ON \
    -DENABLE_DISCORD_RPC=OFF \
    -DENABLE_UPDATER=OFF \
    -DVMA_ENABLE_INSTALL=ON

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

found_bin="$(find "${BUILD}" "${STAGING}" \
    -maxdepth 5 \
    -type f \
    -perm /111 \
    -name 'shadps4' \
    -print -quit 2>/dev/null || true)"

[[ -n "${found_bin}" ]] || die "shadps4 binary was not produced"

cp "${found_bin}" "${STAGING}/bin/shadps4"
chmod +x "${STAGING}/bin/shadps4"
strip "${STAGING}/bin/shadps4" || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
