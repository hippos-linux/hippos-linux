#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='nanoboyadvance'
REPO='https://github.com/nba-emu/NanoBoyAdvance.git'
TAG="${NANOBOYADVANCE_TAG:-$(github_latest_tag "${REPO}")}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

log "Building Qt frontend"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DPLATFORM_QT=ON \
    -DCMAKE_INSTALL_PREFIX="${STAGING}"
cmake --build "${BUILD}" -j"$(nproc)"

find "${BUILD}" -maxdepth 4 -name 'NanoBoyAdvance' -type f -perm /111 \
    -exec cp {} "${STAGING}/bin/nanoboyadvance" \; 2>/dev/null || true
[[ -x "${STAGING}/bin/nanoboyadvance" ]] || die "nanoboyadvance binary was not produced"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
