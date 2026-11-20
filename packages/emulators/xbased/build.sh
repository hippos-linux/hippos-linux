#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='xbased'
REPO='https://github.com/crazyriddler/xbased'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
DEPS="${WORK_ROOT}/${NAME}/deps"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"
bash "${SRC}/tools/fetch_deps.sh" "${DEPS}"

rm -rf "${BUILD}"
cmake -S "${SRC}/native" -B "${BUILD}" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_LINKER_TYPE=LLD \
    -DCMAKE_C_FLAGS="-Wno-error=implicit-function-declaration" \
    -DNC_DEPS="${DEPS}"
cmake --build "${BUILD}" --target xbased -j"$(nproc)"

rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin"
install -m755 "${BUILD}/xbased" "${STAGING}/bin/xbased"
strip "${STAGING}/bin/xbased"
cp -r "${SRC}/native/app/ui/fonts" "${SRC}/mods" "${SRC}/cheats" "${STAGING}/bin/"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
