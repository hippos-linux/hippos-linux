#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='azahar'
REPO='https://github.com/AzaharPlus/AzaharPlus.git'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

# A stale CMakeCache.txt reuses cached *_DIR values from whatever prefix
# resolved them last run instead of re-searching CMAKE_PREFIX_PATH/deps —
# always start clean.
rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DENABLE_QT_TRANSLATION=OFF \
    -DCITRA_ENABLE_BUNDLE_TARGET=OFF \
    -DENABLE_WEB_SERVICE=OFF
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"
find "${BUILD}" -maxdepth 4 -name 'azahar' -type f -perm /111 -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
