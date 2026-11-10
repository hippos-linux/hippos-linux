#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='box64'
REPO='https://github.com/ptitSeb/box64'
TAG="${BOX64_TAG:-$(github_latest_tag "${REPO}")}"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/${ARCH}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

[[ "${ARCH}" == "arm64" ]] || die "box64 runs x86_64 programs on arm64; there is nothing to build for ${ARCH}"

clone_source "${REPO}" "${TAG}" "${SRC}"

rm -rf "${BUILD}" "${STAGING}"
mkdir -p "${BUILD}" "${STAGING}"

log "Configuring ${TAG} for Raspberry Pi 5"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DRPI5ARM64=ON \
    -DNOGIT=ON

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

log "Staging"
DESTDIR="${STAGING}" cmake --install "${BUILD}"
[[ -x "${STAGING}/usr/bin/box64" ]] || die "box64 binary was not staged"
"${STRIP:-strip}" "${STAGING}/usr/bin/box64"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
