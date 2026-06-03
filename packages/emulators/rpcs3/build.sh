#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='rpcs3'
REPO='https://github.com/RPCS3/rpcs3.git'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

if ! grep -q '^#include <QJsonDocument>' "${SRC}/rpcs3/rpcs3qt/downloader.cpp"; then
    sed -i '/^#include <QJsonObject>/a #include <QJsonDocument>' "${SRC}/rpcs3/rpcs3qt/downloader.cpp"
fi

# Clang 19 doesn't always prove fmt::throw_exception [[noreturn]] through all paths.
# Drop the three -Werror flags that fire as a result rather than patching every callsite.
sed -i \
    -e '/add_compile_options(-Werror=return-type)/d' \
    -e '/add_compile_options(-Werror=missing-noreturn)/d' \
    -e '/add_compile_options(-Werror=implicit-fallthrough)/d' \
    "${SRC}/buildfiles/cmake/ConfigureCompiler.cmake"

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=/usr/bin/clang \
    -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
    -DCMAKE_EXE_LINKER_FLAGS="-lstdc++" \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DOpenGL_GL_PREFERENCE=LEGACY \
    -DLLVM_DIR=/usr/lib/llvm-19/lib/cmake/llvm \
    -DUSE_DISCORD_RPC=OFF \
    -DUSE_FAUDIO=ON \
    -DUSE_LIBEVDEV=ON \
    -DUSE_LTO=OFF \
    -DUSE_NATIVE_INSTRUCTIONS=OFF \
    -DUSE_PRECOMPILED_HEADERS=OFF \
    -DUSE_SDL=ON \
    -DUSE_SYSTEM_CURL=ON \
    -DUSE_SYSTEM_FFMPEG=ON \
    -DUSE_SYSTEM_LIBUSB=ON \
    -DUSE_SYSTEM_OPENCV=OFF \
    -DUSE_SYSTEM_SDL=ON \
    -DUSE_VULKAN=ON
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"
find "${BUILD}" -maxdepth 4 -name 'rpcs3' -type f -perm /111 -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
