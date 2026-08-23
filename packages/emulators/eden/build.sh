#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='eden'
REPO='https://github.com/eden-emulator/mirror.git'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build-release"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

_charts_pkg="qt6-charts-dev"
[[ "${ARCH:-amd64}" == "arm64" ]] && _charts_pkg="qt6-charts-dev:arm64"
if ! dpkg -s "${_charts_pkg}" >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y --no-install-recommends "${_charts_pkg}"
fi

rm -rf "${STAGING}"
rm -rf "${BUILD}"
mkdir -p "${STAGING}/bin"

log "Configuring Eden ${TAG}"
cmake -S "${SRC}" -B "${BUILD}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DYUZU_TESTS=OFF \
    -DYUZU_USE_CPM=ON \
    -DYUZU_USE_QT_WEB_ENGINE=OFF \
    -DYUZU_USE_EXTERNAL_VULKAN_SPIRV_TOOLS=OFF \
    -DYUZU_ROOM=OFF \
    -DYUZU_ROOM_STANDALONE=OFF \
    -DENABLE_UPDATE_CHECKER=OFF \
    -DENABLE_WEB_SERVICE=OFF \
    -DUSE_DISCORD_PRESENCE=OFF

log "Building Eden"
cmake --build "${BUILD}" -j"$(nproc)"

if [[ -d "${BUILD}/bin" ]]; then
    cp -a "${BUILD}/bin/." "${STAGING}/bin/"
fi

if [[ ! -x "${STAGING}/bin/eden" && -x "${BUILD}/src/eden" ]]; then
    install -m 0755 "${BUILD}/src/eden" "${STAGING}/bin/eden"
fi

[[ -x "${STAGING}/bin/eden" ]] || die "Eden executable was not produced"
# Stripping is now handled centrally by build/strip-emulator-payload.sh (called from both configure-rootfs.sh and build-emulators.sh).

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
