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

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" \
    -DCMAKE_FIND_PACKAGE_PREFER_CONFIG=ON \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DOPT_TESTS=OFF

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

log "Installing"
cmake --install "${BUILD}"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
