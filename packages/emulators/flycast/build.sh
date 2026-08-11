#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='flycast'
REPO='https://github.com/flyinghead/flycast.git'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

# Build standalone
log "Building standalone"
# A stale CMakeCache.txt reuses cached *_DIR values from whatever prefix
# resolved them last run instead of re-searching CMAKE_PREFIX_PATH/deps —
# always start clean.
rm -rf "${BUILD}"
mkdir -p "${BUILD}/standalone" "${STAGING}/bin"
cmake -S "${SRC}" -B "${BUILD}/standalone" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF \
    -DLIBRETRO=OFF
cmake --build "${BUILD}/standalone" -j"$(nproc)"
cp "${BUILD}/standalone/flycast" "${STAGING}/bin/"
mkdir -p "${STAGING}/lib"
cp /usr/lib/${GNU_ARCH}/libao.so.4* "${STAGING}/lib/" 2>/dev/null || true
patchelf --set-rpath '$ORIGIN/../lib' "${STAGING}/bin/flycast" 2>/dev/null || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
