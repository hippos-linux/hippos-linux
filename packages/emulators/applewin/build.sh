#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='applewin'
REPO='https://github.com/audetto/AppleWin'
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
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="\$ORIGIN/../lib" \
    -DLINUX=ON \
    -DBUILD_QAPPLE=OFF \
    -DBUILD_SA2=ON
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"
find "${BUILD}" -maxdepth 4 -type f -perm /111 -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

mkdir -p "${STAGING}/lib"
cp /usr/lib/x86_64-linux-gnu/libminizip.so.1* "${STAGING}/lib/" 2>/dev/null || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
