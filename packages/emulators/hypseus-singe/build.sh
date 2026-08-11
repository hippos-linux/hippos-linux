#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='hypseus-singe'
REPO='https://github.com/DirtBagXon/hypseus-singe'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

# A stale CMakeCache.txt caches SDL3_DIR/SDL3_image_DIR/SDL3_ttf_DIR from
# whatever prefix resolved them last run; cmake reuses those cache entries on
# reconfigure instead of re-searching CMAKE_PREFIX_PATH, silently pinning the
# emulator back to Trixie's system SDL3 (3.2.10) even when SDL3_mixer
# correctly picks up the newer shared stack. Always start clean.
rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

# hypseus-singe v3.0.1+ requires SDL3_mixer via find_package(... CONFIG REQUIRED),
# which Trixie doesn't package (and Trixie's SDL3 is too old for any packaged
# SDL_mixer release to build against regardless — see build/sdl3-stack-build.sh).
# Pulls in HippOS's shared from-source static SDL3 stack.
source "/work/build/sdl3-stack-env.sh"

# cmake runs the verify script as:
#   cd ${BUILD}/3rdparty/src && cmake -P .../libmpeg2-stamp/verify-libmpeg2.cmake
# cmake -P sets CMAKE_CURRENT_SOURCE_DIR to the CWD (where cmake is invoked),
# so ../../../src/3rdparty/libmpeg2/ resolves from ${BUILD}/3rdparty/src/ up
# three levels to ${WORK_ROOT}/${NAME}/, then into src/3rdparty/libmpeg2/.
_MPEG2_DST="${WORK_ROOT}/${NAME}/src/3rdparty/libmpeg2"
mkdir -p "${_MPEG2_DST}"

if [[ -f "${SRC}/src/3rdparty/libmpeg2/libmpeg2-master.tgz" ]]; then
    log "Using bundled libmpeg2-master.tgz"
    cp "${SRC}/src/3rdparty/libmpeg2/libmpeg2-master.tgz" "${_MPEG2_DST}/"
else
    log "Downloading missing libmpeg2-master.tgz"
    curl -fL \
        "https://github.com/DirtBagXon/hypseus-singe/raw/master/src/3rdparty/libmpeg2/libmpeg2-master.tgz" \
        -o "${_MPEG2_DST}/libmpeg2-master.tgz"
fi

cmake -S "${SRC}/src" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DCMAKE_PREFIX_PATH="${SDL_STACK_ROOT}"

cmake --build "${BUILD}" -j"$(nproc)"

cp "${BUILD}/hypseus" "${STAGING}/bin/" 2>/dev/null || \
    find "${BUILD}" -maxdepth 3 -name 'hypseus' -type f -perm /111 -exec cp {} "${STAGING}/bin/" \;

if [[ ! -x "${STAGING}/bin/hypseus" ]]; then
    die "hypseus binary was not produced"
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
