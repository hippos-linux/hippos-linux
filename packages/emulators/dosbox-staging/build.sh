#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='dosbox-staging'
REPO='https://github.com/dosbox-staging/dosbox-staging'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

mkdir -p "${STAGING}/bin"
meson setup "${BUILD}" "${SRC}" \
    --buildtype=release \
    --prefix="${STAGING}"
meson compile -C "${BUILD}" -j"$(nproc)"
meson install -C "${BUILD}"

# meson strips RPATH on install; re-add so bundled libs are found at runtime
find "${STAGING}/bin" -type f -perm /111 | while read -r b; do
    patchelf --set-rpath '$ORIGIN/../lib/x86_64-linux-gnu:$ORIGIN/../lib' "${b}" 2>/dev/null || true
done

# Copy vendored shared libs (fluidsynth, mt32emu) that meson wrap builds but doesn't install
mkdir -p "${STAGING}/lib/x86_64-linux-gnu"
find "${BUILD}" \( -name "libfluidsynth.so*" -o -name "libmt32emu.so*" \) \
    ! -name "*.a" \
    -exec cp -P {} "${STAGING}/lib/x86_64-linux-gnu/" \; 2>/dev/null || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
