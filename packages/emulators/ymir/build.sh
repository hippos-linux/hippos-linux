#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='ymir'
REPO='https://github.com/StrikerX3/Ymir.git'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

git -C "${SRC}" submodule update --init --recursive

# vcpkg's dbus port has systemd as a default feature → libsystemd → meson needs jinja2.
# apt lists are cleared in the container so apt-get install won't work; use pip.
pip3 install --quiet --break-system-packages jinja2

# vcpkg provides all deps (semver, rtmidi, tomlplusplus, ngtcp2, nghttp3, curl, etc.)
if [[ ! -x "${SRC}/vcpkg/vcpkg" ]]; then
    log "Bootstrapping vcpkg"
    "${SRC}/vcpkg/bootstrap-vcpkg.sh" -disableMetrics
fi

# Overlay triplet: disable SDL_IBUS so SDL3 compiles consistently without ibus
# symbols. The default vcpkg SDL3 build references SDL_IBus_* from SDL_ime.c but
# omits SDL_ibus.c when ibus headers are absent, leaving undefined symbols at link.
TRIPLET_DIR="${SRC}/custom-triplets"
mkdir -p "${TRIPLET_DIR}"
cat > "${TRIPLET_DIR}/x64-linux.cmake" << 'TRIPLET_EOF'
set(VCPKG_TARGET_ARCHITECTURE x64)
set(VCPKG_CRT_LINKAGE dynamic)
set(VCPKG_LIBRARY_LINKAGE static)
set(VCPKG_CMAKE_SYSTEM_NAME Linux)
set(VCPKG_BUILD_TYPE release)
if("${PORT}" STREQUAL "sdl3")
    list(APPEND VCPKG_CMAKE_CONFIGURE_OPTIONS "-DSDL_IBUS=OFF")
endif()
TRIPLET_EOF

# If cached SDL3 is missing SDL_IBus_* symbols (broken build), clear vcpkg
# installed packages so they rebuild with the corrected triplet.
SDL3_LIB="${SRC}/vcpkg_installed/x64-linux/lib/libSDL3.a"
if [[ -f "${SDL3_LIB}" ]] && ! nm "${SDL3_LIB}" 2>/dev/null | grep -q 'SDL_IBus_Quit'; then
    log "SDL3 missing IBus symbols; clearing vcpkg cache for clean rebuild"
    rm -rf "${SRC}/vcpkg_installed"
fi

YMIR_AVX2=OFF
if grep -qw avx2 /proc/cpuinfo 2>/dev/null; then
    YMIR_AVX2=ON
fi

LLVM_AR="$(command -v llvm-ar-19 || command -v llvm-ar || true)"
LLVM_RANLIB="$(command -v llvm-ranlib-19 || command -v llvm-ranlib || true)"

cmake_flags=(
    -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_CXX_SCAN_FOR_MODULES=OFF
    -DCMAKE_TOOLCHAIN_FILE="${SRC}/vcpkg/scripts/buildsystems/vcpkg.cmake"
    -DVCPKG_OVERLAY_TRIPLETS="${TRIPLET_DIR}"
    -DCMAKE_C_COMPILER=clang
    -DCMAKE_CXX_COMPILER=clang++
    -DCMAKE_EXE_LINKER_FLAGS_INIT="-fuse-ld=lld"
    -DCMAKE_MODULE_LINKER_FLAGS_INIT="-fuse-ld=lld"
    -DCMAKE_SHARED_LINKER_FLAGS_INIT="-fuse-ld=lld"
    -DCMAKE_INSTALL_PREFIX="${STAGING}"
    -DBUILD_SHARED_LIBS=OFF
    -DYMIR_BUILD_SANDBOX=OFF
    -DYmir_DEV_BUILD=OFF
    -DYmir_ENABLE_IMGUI_DEMO=OFF
    -DYmir_ENABLE_IPO=ON
    -DYmir_ENABLE_SANDBOX=OFF
    -DYmir_ENABLE_TESTS=OFF
    -DYmir_ENABLE_UPDATE_CHECKS=OFF
    -DYmir_ENABLE_YMDASM=OFF
    -DYmir_INCLUDE_PACKAGING=OFF
    -DYmir_AVX2="${YMIR_AVX2}"
)

if [[ -n "${LLVM_AR}" && -n "${LLVM_RANLIB}" ]]; then
    cmake_flags+=(
        -DCMAKE_AR="${LLVM_AR}"
        -DCMAKE_RANLIB="${LLVM_RANLIB}"
        -DCMAKE_C_COMPILER_AR="${LLVM_AR}"
        -DCMAKE_C_COMPILER_RANLIB="${LLVM_RANLIB}"
        -DCMAKE_CXX_COMPILER_AR="${LLVM_AR}"
        -DCMAKE_CXX_COMPILER_RANLIB="${LLVM_RANLIB}"
    )
fi

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" "${cmake_flags[@]}"

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

log "Installing"
cmake --install "${BUILD}" || true

found_bin="$(find "${BUILD}" "${STAGING}" \
    -maxdepth 6 \
    \( -type f -o -type l \) \
    -perm /111 \
    -name 'ymir-sdl3*' \
    -print -quit 2>/dev/null || true)"

[[ -n "${found_bin}" ]] || die "ymir binary was not produced"

cp "${found_bin}" "${STAGING}/bin/ymir"
chmod +x "${STAGING}/bin/ymir"
strip "${STAGING}/bin/ymir" || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
