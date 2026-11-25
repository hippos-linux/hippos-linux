#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='sonic-mania'
REPO='https://github.com/RSDKModding/Sonic-Mania-Decompilation'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
SHADER_MOD="${STAGING}/share/mods/GLShaders"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

BUILD_PACKAGES=(libsdl2-dev libglew-dev libglfw3-dev libogg-dev libtheora-dev)
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
    -DGAME_STATIC=ON \
    -DUSE_SDL_AUDIO=ON \
    -DRETRO_OUTPUT_NAME="${NAME}"
log "Building Sonic Mania ${TAG} (Plus disabled)"
cmake --build "${BUILD}" -j"$(nproc)"

install -D -m755 "${BUILD}/dependencies/RSDKv5/${NAME}" "${STAGING}/bin/${NAME}"
mkdir -p "${SHADER_MOD}/Data/Shaders/OGL"
cp -a "${SRC}/dependencies/RSDKv5/RSDKv5/Shaders/OGL/." "${SHADER_MOD}/Data/Shaders/OGL/"
printf 'Name=GLShaders\nDescription=OpenGL shaders for RSDKv5\nAuthor=RSDKv5 decompilation\nVersion=1.0.0\nTargetVersion=-1\n' > "${SHADER_MOD}/mod.ini"
install -D -m644 "${SRC}/LICENSE.md" "${STAGING}/share/licenses/Sonic-Mania-Decompilation.md"
install -D -m644 "${SRC}/dependencies/RSDKv5/LICENSE.md" "${STAGING}/share/licenses/RSDKv5-Decompilation.md"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
