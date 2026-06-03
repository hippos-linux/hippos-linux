#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='lightspark'
REPO='https://github.com/lightspark/lightspark'
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
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="\$ORIGIN/../lib/lightspark:\$ORIGIN/../lib" \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCOMPILE_PLUGIN=OFF

cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"

find "${STAGING}" "${BUILD}" \
    -maxdepth 5 \
    -name 'lightspark' \
    -type f \
    -perm /111 \
    -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

if [[ ! -x "${STAGING}/bin/lightspark" ]]; then
    die "lightspark binary was not produced"
fi

find "${STAGING}/bin" -maxdepth 1 -type f -perm /111 | while read -r b; do
    patchelf --set-rpath '$ORIGIN/../lib/lightspark:$ORIGIN/../lib' "${b}" 2>/dev/null || true
done
# Fix shared libs: cmake bakes the Docker-internal absolute install path into RUNPATH.
# Patch them to use $ORIGIN so they find sibling libs at any deployment location.
find "${STAGING}/lib" -name "*.so*" -type f | while read -r lib; do
    patchelf --set-rpath '$ORIGIN' "${lib}" 2>/dev/null || true
done

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
