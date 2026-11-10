#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='sm2-emu'
REPO='https://github.com/dmanlfc/sm2-emu.git'
TAG="${SM2EMU_TAG:-$(github_latest_tag "${REPO}")}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

# imgui, miniz, musashi, ymfm, VulkanMemoryAllocator are submodules; lzma-sdk is
# vendored in-repo. sdl3/shaderc/pugixml/curl/spirv come from the bulk image.
clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

if ! command -v glslc >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y --no-install-recommends glslc
fi

GL_OPTS=(-DSM2_BUILD_OPENGL_DESKTOP=ON)
if [[ "${ARCH}" == "arm64" ]]; then
    GL_OPTS=(-DSM2_BUILD_OPENGL_DESKTOP=OFF -DSM2_BUILD_OPENGL_ES=ON)
fi

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DSM2_BUILD_TESTS=OFF \
    -DSM2_LTO=ON \
    -DSM2_BUILD_VULKAN=ON \
    -DSM2_GLSLC="$(command -v glslc)" \
    "${GL_OPTS[@]}" \
    -DCMAKE_INSTALL_PREFIX="${STAGING}"
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"

if [[ ! -x "${STAGING}/bin/sm2-emu" ]]; then
    found="$(find "${BUILD}" "${STAGING}" -maxdepth 4 -name 'sm2-emu' -type f -perm /111 -print -quit 2>/dev/null || true)"
    [[ -n "${found}" ]] && cp "${found}" "${STAGING}/bin/sm2-emu"
fi
[[ -x "${STAGING}/bin/sm2-emu" ]] || die "sm2-emu binary was not produced"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
