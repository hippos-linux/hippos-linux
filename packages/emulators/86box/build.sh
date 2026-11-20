#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='86box'
REPO='https://github.com/86Box/86Box'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

BUILD_PACKAGES=(libfluidsynth-dev qt6-base-dev qt6-base-private-dev qt6-tools-dev qt6-tools-dev-tools qt6-l10n-tools libvulkan-dev)
missing=()
for package in "${BUILD_PACKAGES[@]}"; do
    dpkg -s "${package}${DEB_TARGET_SUFFIX}" >/dev/null 2>&1 || missing+=("${package}${DEB_TARGET_SUFFIX}")
done
if (( ${#missing[@]} )); then
    apt-get update -qq && apt-get install -y --no-install-recommends "${missing[@]}"
fi

dynarec_args=()
[[ "${ARCH:-amd64}" == "arm64" ]] && dynarec_args=(-DNEW_DYNAREC=ON)

log "Configuring 86Box ${TAG}"
rm -rf "${BUILD}"
cmake -S "${SRC}" -B "${BUILD}" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DQT=ON -DUSE_QT6=ON \
    -DDEV_BRANCH=OFF \
    "${dynarec_args[@]}"
cmake --build "${BUILD}" -j"$(nproc)"

rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin"
install -m755 "${BUILD}/src/86Box" "${STAGING}/bin/86box"
"${STRIP:-strip}" "${STAGING}/bin/86box"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
