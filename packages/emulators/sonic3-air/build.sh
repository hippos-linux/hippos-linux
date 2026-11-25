#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='sonic3-air'
REPO='https://github.com/Eukaryot/sonic3air'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
GAME="${SRC}/Oxygen/sonic3air"
BUILD="${GAME}/build/_cmake/build"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

BUILD_PACKAGES=(libsdl2-dev libgl-dev libglu1-mesa-dev libasound2-dev libpulse-dev libxcomposite-dev libxxf86vm-dev libcurl4-openssl-dev zlib1g-dev)
missing=()
for package in "${BUILD_PACKAGES[@]}"; do
    dpkg -s "${package}${DEB_TARGET_SUFFIX}" >/dev/null 2>&1 || missing+=("${package}${DEB_TARGET_SUFFIX}")
done
if (( ${#missing[@]} )); then
    apt-get update -qq && apt-get install -y --no-install-recommends "${missing[@]}"
fi

rm -rf "${BUILD}" "${STAGING}"
cmake -S "${GAME}/build/_cmake" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DUSE_DISCORD=OFF
log "Building Sonic 3 A.I.R. ${TAG}"
cmake --build "${BUILD}" -j"$(nproc)"

mkdir -p "${STAGING}/bin" "${STAGING}/oxygenengine"
install -m755 "${GAME}/sonic3air_linux" "${STAGING}/bin/sonic3air_linux"
cp -a "${GAME}/config.json" "${GAME}/oxygenproject.json" "${GAME}/data" "${GAME}/scripts" "${GAME}/saves" "${STAGING}/bin/"
cp -a "${SRC}/Oxygen/oxygenengine/data" "${STAGING}/oxygenengine/"
install -m644 "${SRC}/LICENSE" "${STAGING}/LICENSE"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
