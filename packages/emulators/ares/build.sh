#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='ares'
REPO='https://github.com/ares-emulator/ares'
TAG="$(github_latest_tag "${REPO}")"

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

cmake -S "${SRC}" -B "${BUILD}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DUSE_QT6=ON \
    -DARES_SKIP_DEPS=ON

cmake --build "${BUILD}" -j"$(nproc)"

# Binary lands in build/rundir/bin/ares after cmake build
ARES_BIN="$(find "${BUILD}" -maxdepth 5 -name 'ares' -type f -perm /111 | head -1)"
[[ -n "${ARES_BIN}" ]] || die "ares binary not found after build"
log "Binary: ${ARES_BIN}"
cp "${ARES_BIN}" "${STAGING}/bin/ares"
mkdir -p "${STAGING}/lib"
cp /usr/lib/x86_64-linux-gnu/libao.so.4* "${STAGING}/lib/" 2>/dev/null || true
patchelf --set-rpath '$ORIGIN/../lib' "${STAGING}/bin/ares" 2>/dev/null || true

# Copy any bundled data/shaders alongside the binary
RUNDIR="$(dirname "${ARES_BIN}")"
if [[ -d "${RUNDIR}/shaders" ]]; then
    cp -r "${RUNDIR}/shaders" "${STAGING}/"
fi
if [[ -d "${RUNDIR}/System" ]]; then
    cp -r "${RUNDIR}/System" "${STAGING}/"
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
