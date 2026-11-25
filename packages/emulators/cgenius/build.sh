#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='cgenius'
REPO='https://github.com/gerstrong/Commander-Genius'
TAG='v3.6.4'

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

BUILD_PACKAGES=(libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libcurl4-openssl-dev zlib1g-dev libgl-dev xxd)
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
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DDEBUG=OFF \
    -DBUILD_COSMOS=ON \
    -DUSE_OPENGL=ON \
    -DUSE_CRASHHANDLER=OFF \
    -DUSE_VIRTUALPAD=OFF
log "Building Commander Genius ${TAG}"
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"
if [[ -f "${STAGING}/games/CGeniusExe" ]]; then
    install -D -m755 "${STAGING}/games/CGeniusExe" "${STAGING}/bin/CGeniusExe"
    rm "${STAGING}/games/CGeniusExe"
fi
rmdir --ignore-fail-on-non-empty "${STAGING}/games" 2>/dev/null || true

cp "${SRC}/LICENSE" "${STAGING}/LICENSE"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
