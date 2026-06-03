#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"
source "/work/build/qt611-env.sh"

NAME='eka2l1'
REPO='https://github.com/EKA2L1/EKA2L1.git'

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO}"
    git clone --depth=1 "${REPO}" "${SRC}"
fi

# Remove Android-only submodules not needed for Linux build
git -C "${SRC}" config -f "${SRC}/.gitmodules" --remove-section submodule.dynarmic-android 2>/dev/null || true
git -C "${SRC}" config -f "${SRC}/.gitmodules" --remove-section submodule.ext-boost 2>/dev/null || true
git -C "${SRC}" submodule sync
git -C "${SRC}" submodule update --init --recursive

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="-Wno-incompatible-pointer-types -Wno-int-conversion" \
    -DCMAKE_CXX_FLAGS="-include algorithm -I${QT_ROOT}/include/QtGui/6.11.1/QtGui" \
    -DCMAKE_PREFIX_PATH="${QT_ROOT}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="/opt/hippos/qt/6.11/lib:\$ORIGIN/../lib" \
    -DBUILD_SHARED_LIBS=OFF \
    -DBUILD_STATIC_LIBS=ON \
    -DEKA2L1_ENABLE_SCRIPTING_ABILITY=OFF \
    -DEKA2L1_BUILD_TOOLS=OFF \
    -DEKA2L1_BUILD_TESTS=OFF \
    -DEKA2L1_USE_SYSTEM_FFMPEG=ON \
    -DEKA2L1_UNIX_USE_X11=ON \
    -DEKA2L1_UNIX_USE_WAYLAND=OFF \
    -DENABLE_PROGRAMS=OFF

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

if [[ ! -x "${BUILD}/bin/eka2l1_qt" ]]; then
    die "eka2l1_qt binary was not produced"
fi

cp -a "${BUILD}/bin/." "${STAGING}/bin/"
find "${STAGING}/bin" -maxdepth 1 -type f -perm /111 -exec strip {} \; 2>/dev/null || true

write_artifact_version "${STAGING}" "$(git -C "${SRC}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
