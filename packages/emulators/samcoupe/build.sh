#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='samcoupe'
REPO='https://github.com/simonowen/simcoupe'
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
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="\$ORIGIN/../lib"
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"
find "${BUILD}" -maxdepth 4 -name 'simcoupe' -type f -perm /111 -exec cp {} "${STAGING}/bin/samcoupe" \; 2>/dev/null || true

if [[ ! -x "${STAGING}/bin/samcoupe" ]]; then
    die "samcoupe binary was not produced"
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
