#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='fallout1-ce'
REPO='https://github.com/alexbatalov/fallout1-ce'
TAG='v1.1.0'

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

BUILD_PACKAGES=(libsdl2-dev zlib1g-dev)
missing=()
for package in "${BUILD_PACKAGES[@]}"; do
    dpkg -s "${package}${DEB_TARGET_SUFFIX}" >/dev/null 2>&1 || missing+=("${package}${DEB_TARGET_SUFFIX}")
done
if (( ${#missing[@]} )); then
    apt-get update -qq && apt-get install -y --no-install-recommends "${missing[@]}"
fi

rm -rf "${BUILD}" "${STAGING}"
cmake -S "${SRC}" -B "${BUILD}" -DCMAKE_BUILD_TYPE=Release
log "Building ${NAME} ${TAG}"
cmake --build "${BUILD}" -j"$(nproc)"
install -D -m755 "${BUILD}/fallout-ce" "${STAGING}/bin/${NAME}"
install -D -m644 "${SRC}/LICENSE.md" "${STAGING}/LICENSE.md"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
