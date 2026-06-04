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

PATCH_DIR="${REPO_ROOT}/packages/emulators/${NAME}"
for patch in 001-sdl3-haptic-effect-id.patch; do
    if git -C "${SRC}" apply --reverse --check "${PATCH_DIR}/${patch}" >/dev/null 2>&1; then
        log "Patch already applied: ${patch}"
    else
        git -C "${SRC}" apply "${PATCH_DIR}/${patch}"
    fi
done

if ! grep -q '^#include <QJsonDocument>' "${SRC}/rpcs3/rpcs3qt/downloader.cpp"; then
    sed -i '/^#include <QJsonObject>/a #include <QJsonDocument>' "${SRC}/rpcs3/rpcs3qt/downloader.cpp"
fi

if ! grep -q '^#include <QJsonDocument>' "${SRC}/rpcs3/rpcs3qt/config_database.cpp"; then
    sed -i '1s|^|#include <QJsonDocument>\n#include <QJsonParseError>\n|' "${SRC}/rpcs3/rpcs3qt/config_database.cpp"
fi

if ! grep -q '^#include <unordered_set>' "${SRC}/rpcs3/rpcs3qt/game_list_frame.h"; then
    sed -i '/^#include <set>/a #include <unordered_set>' "${SRC}/rpcs3/rpcs3qt/game_list_frame.h"
fi

# SDL3 < 3.2.12: no SDL_CameraPermissionState enum; SDL_GetCameraPermissionState returns int.
# Replace scoped enum usage and substitute constants with their integer values (-1, 0, 1).
sed -i \
    -e 's/SDL_CameraPermissionState:://g' \
    -e 's/SDL_CAMERA_PERMISSION_STATE_DENIED/-1/g' \
    -e 's/SDL_CAMERA_PERMISSION_STATE_PENDING/0/g' \
    -e 's/SDL_CAMERA_PERMISSION_STATE_APPROVED/1/g' \
    "${SRC}/rpcs3/Input/sdl_camera_handler.cpp"

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
