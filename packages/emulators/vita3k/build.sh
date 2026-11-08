#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"
source "/work/build/qt-env.sh"

NAME='vita3k'
REPO='https://github.com/vita3k/vita3k'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

# Reset all submodule contents to their committed state.
# Previous runs may have incorrectly patched C++ libraries (yaml-cpp, psvpfstools, etc.)
# that use std::uint8_t etc., breaking their compilation.
git -C "${SRC}" submodule foreach --recursive \
    'git restore . 2>/dev/null || git checkout -- . 2>/dev/null || true' 2>/dev/null || true

# Patch only known C libraries that incorrectly include <cstdint> (a C++-only header).
# capstone: generated .inc files; external/sdl: SDL3 headers included by C translation units.
for target_dir in "${SRC}/external/capstone" "${SRC}/external/sdl"; do
    [[ -d "${target_dir}" ]] || continue
    while IFS= read -r f; do
        log "Fixing <cstdint> in: ${f}"
        sed -i 's|#include <cstdint>|#include <stdint.h>|g' "${f}"
    done < <(find "${target_dir}" \
        \( -name '*.c' -o -name '*.h' -o -name '*.inc' \) \
        -exec grep -l '#include <cstdint>' {} \; 2>/dev/null || true)
done

# GCC 13+ rejects duplicate cv-qualifiers as an error.
# Patch the offending line before configuring.
LOAD_SELF="${SRC}/vita3k/kernel/src/load_self.cpp"
if [[ -f "${LOAD_SELF}" ]]; then
    sed -i 's/reinterpret_cast<const Elf32_Phdr const \*>/reinterpret_cast<const Elf32_Phdr *>/g' "${LOAD_SELF}"
fi

# std::vector::append_range/assign_range are C++23 library features that
# Trixie's libstdc++ 14 lacks (they arrived in GCC 15).
VECTOR_UTILS="${SRC}/vita3k/util/include/util/vector_utils.h"
sed -i -E \
    -e 's/(\w+)\.append_range\((\w+)\);/\1.insert(\1.end(), \2.begin(), \2.end());/' \
    -e 's/(\w+)\.assign_range\((\w+)\);/\1.assign(\2.begin(), \2.end());/' \
    "${VECTOR_UTILS}"

# A stale CMakeCache.txt reuses cached *_DIR values from whatever prefix
# resolved them last run instead of re-searching CMAKE_PREFIX_PATH/deps —
# always start clean.
rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

if grep -q 'XXH_X86DISPATCH_ALLOW_AVX' "${SRC}/CMakeLists.txt"; then
    if grep -qi 'avx2' /proc/cpuinfo; then
        AVX_FLAG='ON'
    else
        AVX_FLAG='OFF'
    fi
else
    AVX_FLAG='OFF'
fi

cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DUSE_DISCORD_RICH_PRESENCE=OFF \
    -DUSE_VITA3K_UPDATE=OFF \
    -DXXH_X86DISPATCH_ALLOW_AVX="${AVX_FLAG}"

# SDL_build_config.h and similar headers are generated into the build tree during cmake
# configure. Patch only files under the SDL build dir to avoid breaking C++ generated headers.
while IFS= read -r f; do
    log "Fixing <cstdint> in generated: ${f}"
    sed -i 's|#include <cstdint>|#include <stdint.h>|g' "${f}"
done < <(find "${BUILD}/external/sdl" "${BUILD}/external/SDL" \
    \( -name '*.c' -o -name '*.h' \) \
    -exec grep -l '#include <cstdint>' {} \; 2>/dev/null || true)

cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"

find "${BUILD}" "${STAGING}" \
    -maxdepth 5 \
    -name 'Vita3K' \
    -type f \
    -perm /111 \
    -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

if [[ ! -x "${STAGING}/bin/Vita3K" ]]; then
    die "Vita3K binary was not produced"
fi

log "Staging runtime data directories alongside binary"
for dir in data icons shaders-builtin translations; do
    src="${BUILD}/bin/${dir}"
    [[ -d "${src}" ]] && rsync -a "${src}/" "${STAGING}/bin/${dir}/" \
        && log "Staged bin/${dir}/" || log "Warning: ${dir}/ not found in build"
done

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
