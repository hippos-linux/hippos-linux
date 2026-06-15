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

if [[ "${ARCH:-amd64}" == "arm64" ]]; then
    log "SKIP: vpinball standalone build uses a linux-x64-only CMakeLists with hardcoded x86 SIMD flags; no arm64 build available"
    exit 0
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

log "Preparing external Linux x64 dependencies"
chmod +x standalone/linux-x64/external.sh
# bass24-linux.zip puts bass.h at c/bass.h (not root); patch each sub-library external.sh
# call in the main script so the sub-script is fixed before it runs.
# Also fix libserum_concentrate repo rename: GitHub now extracts as libserum-SHA/ not
# libserum_concentrate-SHA/.
python3 - <<'PYEOF'
import re

with open('standalone/linux-x64/external.sh', 'r') as f:
    content = f.read()

def inject(m):
    indent = re.match(r'^\s*', m.group(0)).group(0)
    fixes = [
        "sed -i 's|cp bass\\.h |cp c/bass.h |g' platforms/linux/x64/external.sh",
        "sed -i 's|mv libserum_concentrate-|mv libserum-|g' platforms/linux/x64/external.sh",
    ]
    return '\n'.join(indent + f for f in fixes) + '\n' + m.group(0)

content = re.sub(r'^\s*platforms/linux/x64/external\.sh\b', inject, content, flags=re.MULTILINE)

with open('standalone/linux-x64/external.sh', 'w') as f:
    f.write(content)
PYEOF

# external.sh uses relative paths — must run from its own directory so SDL2/SDL_image/etc.
# land at standalone/linux-x64/external/ which is what CMakeLists_gl-linux-x64.txt expects
cd "${SRC}/standalone/linux-x64"
./external.sh
cd "${SRC}"

cp standalone/cmake/CMakeLists_gl-linux-x64.txt CMakeLists.txt

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
strip "${STAGING}/bin/vpinball" || true

# Copy external shared libs that POST_BUILD_COPY_EXT_LIBS=OFF skipped
EXT_LIB="${SRC}/standalone/linux-x64/external/lib"
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
