#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='vpinball'
REPO='https://github.com/vpinball/vpinball.git'
REF="${VPINBALL_REF:-standalone}"
# Pinned: latest standalone HEAD's external.sh references a libserum_concentrate SHA that 404s.
# This SHA (Sep 27, 2025) has a known-working external.sh.
SHA="${VPINBALL_SHA:-3ec37c7f9a7f57168802ca7bbb3fd9f6b745bdc3}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

case "${ARCH:-amd64}" in
    arm64) VPX_ARCH="aarch64" ;;
    *)     VPX_ARCH="x64" ;;
esac
VPX_PLATFORM="linux-${VPX_ARCH}"

if [[ "${CROSS_BUILD}" -eq 1 ]]; then
    mkdir -p "${WORK_ROOT}/${NAME}"
    printf 'host_alias=%s\n' "${GNU_ARCH}" > "${WORK_ROOT}/${NAME}/config.site"
    export CONFIG_SITE="${WORK_ROOT}/${NAME}/config.site"
fi

if [[ -d "${SRC}/.git" ]]; then
    current_sha="$(git -C "${SRC}" rev-parse HEAD 2>/dev/null || echo 'unknown')"
    if [[ "${current_sha}" != "${SHA}" ]]; then
        log "SHA mismatch (have '${current_sha}', need '${SHA}'), re-cloning"
        rm -rf "${SRC}"
    fi
fi

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${REF}"
    git clone --depth=1 --branch "${REF}" "${REPO}" "${SRC}"
    if [[ "$(git -C "${SRC}" rev-parse HEAD)" != "${SHA}" ]]; then
        log "Fetching pinned SHA ${SHA}"
        git -C "${SRC}" fetch --depth=1 origin "${SHA}"
        git -C "${SRC}" checkout "${SHA}"
    fi
    git -C "${SRC}" submodule update --init --recursive
fi

cd "${SRC}"

log "Preparing external ${VPX_PLATFORM} dependencies"
chmod +x "standalone/${VPX_PLATFORM}/external.sh"
# bass24-linux.zip puts bass.h at c/bass.h (not root); patch each sub-library external.sh
# call in the main script so the sub-script is fixed before it runs.
# Also fix libserum_concentrate repo rename: GitHub now extracts as libserum-SHA/ not
# libserum_concentrate-SHA/.
FFMPEG_CROSS_ARGS=""
if [[ "${CROSS_BUILD}" -eq 1 ]]; then
    FFMPEG_CROSS_ARGS="--enable-cross-compile --arch=${VPX_ARCH} --target-os=linux --cross-prefix=${GNU_ARCH}-"
fi
python3 - "${VPX_ARCH}" "${FFMPEG_CROSS_ARGS}" <<'PYEOF'
import re
import sys

arch, ffmpeg_cross_args = sys.argv[1], sys.argv[2]
script = f'standalone/linux-{arch}/external.sh'

with open(script, 'r') as f:
    content = f.read()

def inject(m):
    indent = re.match(r'^\s*', m.group(0)).group(0)
    fixes = [
        f"sed -i 's|cp bass\\.h |cp c/bass.h |g' platforms/linux/{arch}/external.sh",
        f"sed -i 's|mv libserum_concentrate-|mv libserum-|g' platforms/linux/{arch}/external.sh",
    ]
    return '\n'.join(indent + f for f in fixes) + '\n' + m.group(0)

content = re.sub(rf'^\s*platforms/linux/{arch}/external\.sh\b', inject, content, flags=re.MULTILINE)

if ffmpeg_cross_args and ffmpeg_cross_args not in content:
    ffmpeg = content.index('cd FFmpeg-')
    doc = content.index('--disable-doc', ffmpeg)
    content = content[:doc] + f'{ffmpeg_cross_args} ' + content[doc:]

with open(script, 'w') as f:
    f.write(content)
PYEOF

# external.sh uses relative paths — must run from its own directory so SDL2/SDL_image/etc.
# land at standalone/<platform>/external/ which is what CMakeLists_gl-<platform>.txt expects
cd "${SRC}/standalone/${VPX_PLATFORM}"
./external.sh
cd "${SRC}"

cp "standalone/cmake/CMakeLists_gl-${VPX_PLATFORM}.txt" CMakeLists.txt

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF \
    -DPOST_BUILD_COPY_EXT_LIBS=OFF \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_EXE_LINKER_FLAGS="-Wl,-rpath,\$ORIGIN/../lib"

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

if [[ ! -x "${BUILD}/VPinballX_GL" ]]; then
    die "VPinballX_GL binary was not produced"
fi

cp "${BUILD}/VPinballX_GL" "${STAGING}/bin/vpinball"
chmod +x "${STAGING}/bin/vpinball"
# Stripping (including the bundled lib/*.so fetched by external.sh) is now
# handled centrally by build/strip-emulator-payload.sh (called from both
# configure-rootfs.sh and build-emulators.sh).

# Copy external shared libs that POST_BUILD_COPY_EXT_LIBS=OFF skipped
EXT_LIB="${SRC}/standalone/${VPX_PLATFORM}/external/lib"
if [[ -d "${EXT_LIB}" ]]; then
    mkdir -p "${STAGING}/lib"
    find "${EXT_LIB}" -maxdepth 1 \( -name "*.so" -o -name "*.so.*" \) | while read -r f; do
        cp -P "${f}" "${STAGING}/lib/"
    done
fi

for d in flexdmd assets scripts; do
    [[ -d "${BUILD}/${d}" ]] && cp -r "${BUILD}/${d}" "${STAGING}/" || true
done
find "${BUILD}" -maxdepth 1 -name 'shader*' -type d -exec cp -r {} "${STAGING}/" \; || true

write_artifact_version "${STAGING}" "${SHA}"
log "Done. Artifact at ${STAGING}"
