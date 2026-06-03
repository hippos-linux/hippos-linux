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

mkdir -p "${BUILD}" "${STAGING}/bin"

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
    -DCMAKE_INSTALL_PREFIX="${STAGING}"

cmake --build "${BUILD}" -j"$(nproc)"

cp "${BUILD}/hypseus" "${STAGING}/bin/" 2>/dev/null || \
    find "${BUILD}" -maxdepth 3 -name 'hypseus' -type f -perm /111 -exec cp {} "${STAGING}/bin/" \;

if [[ ! -x "${STAGING}/bin/hypseus" ]]; then
    die "hypseus binary was not produced"
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
