#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='ppsspp'
REPO='https://github.com/hrydgard/ppsspp.git'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

mkdir -p "${BUILD}" "${STAGING}/bin"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DUSE_SYSTEM_FFMPEG=OFF \
    -DUSE_SYSTEM_LIBZIP=OFF \
    -DUSE_DISCORD=OFF \
    -DUSING_QT_UI=OFF \
    -DHEADLESS=OFF
cmake --build "${BUILD}" -j"$(nproc)"
cp "${BUILD}/PPSSPPSDL" "${STAGING}/bin/"

# Assets are required at runtime — copy from source tree
cp -r "${SRC}/assets" "${STAGING}/"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
