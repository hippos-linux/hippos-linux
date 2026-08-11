#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='thextech'
REPO='https://github.com/Wohlstand/TheXTech'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

# A stale CMakeCache.txt reuses cached *_DIR values from whatever prefix
# resolved them last run instead of re-searching CMAKE_PREFIX_PATH/deps —
# always start clean.
rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="\$ORIGIN/../lib" \
    -DTHEXTECH_BUILD_TESTS=OFF
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"
find "${BUILD}" -maxdepth 4 -name 'thextech' -type f -perm /111 -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

# Move all libSDL2_mixer_ext files to lib/ regardless of install subdir.
# cmake install only delivers the dev symlink (.so); also copy the real versioned
# lib from the build tree so the binary's $ORIGIN/../lib rpath can resolve it.
mkdir -p "${STAGING}/lib"
find "${STAGING}" ! -path "${STAGING}/lib/*" -name "libSDL2_mixer_ext*" \
    -exec mv {} "${STAGING}/lib/" \; 2>/dev/null || true
find "${BUILD}" -name "libSDL2_mixer_ext.so.*" -type f \
    -exec cp -n {} "${STAGING}/lib/" \; 2>/dev/null || true
# Ensure soname symlink (.so.2 → .so.2.x.x) exists for runtime linker
(cd "${STAGING}/lib" && \
    versioned="$(ls libSDL2_mixer_ext.so.*.*.* 2>/dev/null | head -1)" && \
    [[ -n "${versioned}" ]] && \
    soname="$(echo "${versioned}" | grep -oP 'libSDL2_mixer_ext\.so\.\d+')" && \
    [[ -n "${soname}" && ! -e "${soname}" ]] && \
    ln -sf "${versioned}" "${soname}") 2>/dev/null || true

# Fix RPATH — cmake flag doesn't stick for this project
find "${STAGING}/bin" -maxdepth 1 -type f -perm /111 | while read -r b; do
    patchelf --set-rpath '$ORIGIN/../lib' "${b}" 2>/dev/null || true
done

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
