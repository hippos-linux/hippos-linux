#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='jazz2-native'
REPO='https://github.com/deathkiller/jazz2-native'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
INSTALLED="/opt/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

BUILD_PACKAGES=(libsdl2-dev libopenal-dev libopenmpt-dev libglew-dev libcurl4-openssl-dev zlib1g-dev)
missing=()
for package in "${BUILD_PACKAGES[@]}"; do
    dpkg -s "${package}${DEB_TARGET_SUFFIX}" >/dev/null 2>&1 || missing+=("${package}${DEB_TARGET_SUFFIX}")
done
if (( ${#missing[@]} )); then
    apt-get update -qq && apt-get install -y --no-install-recommends "${missing[@]}"
fi

rm -rf "${BUILD}" "${STAGING}"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${INSTALLED}" \
    -DNCINE_DOWNLOAD_DEPENDENCIES=OFF \
    -DNCINE_PREFERRED_BACKEND=SDL2 \
    -DNCINE_LINUX_PACKAGE=jazz2
log "Building Jazz² Resurrection ${TAG}"
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}" --prefix "${STAGING}"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
