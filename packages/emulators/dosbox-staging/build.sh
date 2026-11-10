#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='dosbox-staging'
REPO='https://github.com/dosbox-staging/dosbox-staging'
VCPKG_REPO='https://github.com/microsoft/vcpkg.git'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
VCPKG_ROOT="${WORK_ROOT}/${NAME}/vcpkg"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

# Upstream dropped its Meson build in favour of CMake + a vcpkg manifest, and
# Debian lacks several manifest deps (iir1, libmt32emu, zlib-ng). Pin vcpkg to
# the manifest's builtin-baseline so port versions match upstream CI.
VCPKG_BASELINE="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["builtin-baseline"])' "${SRC}/vcpkg.json")"
if [[ ! -d "${VCPKG_ROOT}/.git" ]]; then
    git clone --filter=blob:none "${VCPKG_REPO}" "${VCPKG_ROOT}"
fi
if [[ "$(git -C "${VCPKG_ROOT}" rev-parse HEAD)" != "${VCPKG_BASELINE}" ]]; then
    git -C "${VCPKG_ROOT}" fetch origin
    git -C "${VCPKG_ROOT}" checkout --force "${VCPKG_BASELINE}"
    rm -f "${VCPKG_ROOT}/vcpkg"
fi
if [[ ! -x "${VCPKG_ROOT}/vcpkg" ]]; then
    log "Bootstrapping vcpkg"
    "${VCPKG_ROOT}/bootstrap-vcpkg.sh" -disableMetrics
fi

# The manifest's overlay libsystemd port (pulled in by sdl2[dbus]) builds with
# meson, which needs jinja2. apt lists are cleared in the container; use pip.
pip3 install --quiet --break-system-packages jinja2

rm -rf "${BUILD}"
mkdir -p "${STAGING}/bin"

vcpkg_cross_args=()
configure_env=()
if [[ "${CROSS_BUILD}" -eq 1 ]]; then
    TRIPLET_DIR="${WORK_ROOT}/${NAME}/triplets"
    mkdir -p "${TRIPLET_DIR}"
    cat > "${TRIPLET_DIR}/arm64-linux.cmake" << 'TRIPLET_EOF'
set(VCPKG_TARGET_ARCHITECTURE arm64)
set(VCPKG_CRT_LINKAGE dynamic)
set(VCPKG_LIBRARY_LINKAGE static)
set(VCPKG_CMAKE_SYSTEM_NAME Linux)
if("${PORT}" STREQUAL "dbus")
    list(APPEND VCPKG_CMAKE_CONFIGURE_OPTIONS "-DDBUS_SESSION_SOCKET_DIR=/tmp")
endif()
TRIPLET_EOF
    vcpkg_cross_args=(
        -DVCPKG_OVERLAY_TRIPLETS="${TRIPLET_DIR}"
        -DVCPKG_TARGET_TRIPLET=arm64-linux
        -DVCPKG_HOST_TRIPLET=x64-linux
        -DVCPKG_CHAINLOAD_TOOLCHAIN_FILE=/opt/hippos/aarch64-toolchain.cmake
    )
    configure_env=(-u CC -u CXX -u AR)
fi

log "Configuring"
env "${configure_env[@]+"${configure_env[@]}"}" cmake -S "${SRC}" -B "${BUILD}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" \
    -DCMAKE_FIND_PACKAGE_PREFER_CONFIG=ON \
    -DCMAKE_INSTALL_PREFIX="${EMULATOR_RUNTIME_ROOT}/${NAME}" \
    -DOPT_TESTS=OFF \
    "${vcpkg_cross_args[@]+"${vcpkg_cross_args[@]}"}"

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

log "Installing"
install_staged "${NAME}" "${STAGING}" "${BUILD}/destdir" cmake --install "${BUILD}"

# The install puts data under share/dosbox-staging/resources/, but the binary
# looks for share/dosbox-staging/<shaders|freedos-cpi|...>, so without this it
# aborts on its default CRT shader.
RESOURCES="${STAGING}/share/dosbox-staging/resources"
if [[ -d "${RESOURCES}" ]]; then
    cp -a "${RESOURCES}/." "${STAGING}/share/dosbox-staging/"
    rm -rf "${RESOURCES}"
fi
[[ -f "${STAGING}/share/dosbox-staging/shaders/crt/crt-hyllian.glsl" ]] \
    || { log "shaders missing from share/dosbox-staging after install"; exit 1; }

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
