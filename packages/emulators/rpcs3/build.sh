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

# rpcs3 needs SDL3 >= 3.2.12 for SDL_CameraPermissionState (used unmodified,
# below); Trixie ships 3.2.10. Pulls in HippOS's shared from-source static
# SDL3 stack instead of Trixie's package — USE_SYSTEM_SDL stays ON since this
# is still "use an externally-provided SDL3, don't vendor your own", it's just
# not literally the system package anymore.
source "/work/build/sdl3-stack-env.sh"

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

# game_list_actions.cpp: one QString::arg(std::string) callsite is missing the
# QString::fromStdString() wrap used at every other callsite in this file —
# QString::arg has no std::string overload on this Qt version.
sed -i \
    -e 's/\.arg(m_game_validator->get_name())/.arg(QString::fromStdString(m_game_validator->get_name()))/' \
    "${SRC}/rpcs3/rpcs3qt/game_list_actions.cpp"

# basic_keyboard_handler.cpp calls xkb_context_new/unref (base libxkbcommon)
# directly, but CMake only links xkbcommon-x11 — modern ld won't resolve the
# base symbols transitively through it. Link xkbcommon explicitly too.
sed -i \
    -e 's/target_link_libraries(rpcs3_lib PRIVATE X11::X11 xkbcommon-x11)/target_link_libraries(rpcs3_lib PRIVATE X11::X11 xkbcommon-x11 xkbcommon)/' \
    "${SRC}/rpcs3/CMakeLists.txt"

# Clang doesn't always prove fmt::throw_exception [[noreturn]] through all paths.
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
    -DCMAKE_C_COMPILER=/usr/bin/clang-21 \
    -DCMAKE_CXX_COMPILER=/usr/bin/clang++-21 \
    -DCMAKE_EXE_LINKER_FLAGS="-lstdc++" \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_PREFIX_PATH="${SDL_STACK_ROOT}" \
    -DOpenGL_GL_PREFERENCE=LEGACY \
    -DLLVM_DIR=/usr/lib/llvm-21/lib/cmake/llvm \
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
    -DUSE_VULKAN=ON \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="\$ORIGIN/../lib"
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"
find "${BUILD}" -maxdepth 4 -name 'rpcs3' -type f -perm /111 -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

# rpcs3's LLVM recompiler backend links libLLVM.so.21.1 from the build
# container's apt.llvm.org llvm-21 toolchain (LLVM_DIR above) — the shipped
# rootfs only carries Trixie's own llvm-19, and per package-policy.md a
# build-only toolchain dependency has no business becoming a base-OS package
# just for this one emulator, so vendor it next to the binary instead.
mkdir -p "${STAGING}/lib"
cp "/usr/lib/${GNU_ARCH}/libLLVM.so.21.1" "${STAGING}/lib/"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
