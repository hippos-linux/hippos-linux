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

PATCH_DIR="${REPO_ROOT}/packages/emulators/${NAME}"
for patch in 001-multiplayer-join-option.patch; do
    if git -C "${SRC}" apply --reverse --check "${PATCH_DIR}/${patch}" >/dev/null 2>&1; then
        log "Patch already applied: ${patch}"
    else
        git -C "${SRC}" apply "${PATCH_DIR}/${patch}"
    fi
done

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
