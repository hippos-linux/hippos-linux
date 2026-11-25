#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='soniccd'
REPO='https://github.com/RSDKModding/RSDKv3-Decompilation'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

BUILD_PACKAGES=(libsdl2-dev libglew-dev libogg-dev libvorbis-dev libtheora-dev)
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
    -DRETRO_DISABLE_PLUS=ON \
    -DRETRO_SDL_VERSION=2 \
    -DRETRO_OUTPUT_NAME="${NAME}"
log "Building Sonic CD ${TAG} (Plus disabled)"
cmake --build "${BUILD}" -j"$(nproc)"

install -D -m755 "${BUILD}/${NAME}" "${STAGING}/bin/${NAME}"
install -D -m644 "${SRC}/LICENSE.md" "${STAGING}/share/licenses/RSDKv3-Decompilation.md"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
