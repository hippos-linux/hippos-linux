#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='cemu'
REPO='https://github.com/cemu-project/Cemu'
TAG="$(github_latest_tag "${REPO}")"

WX_REPO='https://github.com/wxWidgets/wxWidgets'
WX_TAG='v3.2.10'

HIDAPI_REPO='https://github.com/libusb/hidapi'
HIDAPI_TAG="$(github_latest_tag "${HIDAPI_REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"

HIDAPI_SRC="${WORK_ROOT}/${NAME}/hidapi/source"
HIDAPI_BUILD="${WORK_ROOT}/${NAME}/hidapi/build"
HIDAPI_PREFIX="${WORK_ROOT}/${NAME}/hidapi/install"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

WX_SRC="${WORK_ROOT}/${NAME}/wxwidgets/source"
WX_BUILD="${WORK_ROOT}/${NAME}/wxwidgets/build"
WX_PREFIX="${WORK_ROOT}/${NAME}/wxwidgets/install"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

source "/work/build/sdl3-stack-env.sh"

log "Installing build dependencies"
if apt-get update -qq && apt-get install -y --no-install-recommends \
    libexpat1-dev \
    libzarchive-dev; then
    log "Inline dependency install completed"
else
    log "Skipping inline dependency install; relying on the container image"
fi

clone_source "${HIDAPI_REPO}" "${HIDAPI_TAG}" "${HIDAPI_SRC}"
cmake -S "${HIDAPI_SRC}" -B "${HIDAPI_BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${HIDAPI_PREFIX}" \
    -DHIDAPI_WITH_HIDRAW=ON \
    -DHIDAPI_WITH_LIBUSB=ON \
    -DBUILD_SHARED_LIBS=OFF
cmake --build "${HIDAPI_BUILD}" -j"$(nproc)"
cmake --install "${HIDAPI_BUILD}"

clone_source "${WX_REPO}" "${WX_TAG}" "${WX_SRC}" --submodules
git config --global --add safe.directory "${WX_SRC}" 2>/dev/null || true
if [[ "$(cat "${WX_PREFIX}/.wx-tag" 2>/dev/null)" != "${WX_TAG}" ]]; then
    rm -rf "${WX_BUILD}" "${WX_PREFIX}"
fi

cmake -S "${WX_SRC}" -B "${WX_BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${WX_PREFIX}" \
    -DwxBUILD_SHARED=OFF \
    -DwxUSE_OPENGL=ON \
    -DwxUSE_PROPGRID=ON \
    -DwxUSE_XRC=ON
cmake --build "${WX_BUILD}" -j"$(nproc)"
cmake --install "${WX_BUILD}"
echo "${WX_TAG}" > "${WX_PREFIX}/.wx-tag"

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

python3 - "${SRC}" <<'PYEOF'
import sys
from pathlib import Path

src = Path(sys.argv[1])

files_to_patch = [
    'src/gui/debugger/DumpCtrl.cpp',
    'src/gui/debugger/DisasmCtrl.cpp',
    'src/gui/debugger/RegisterCtrl.cpp',
    'src/gui/debugger/RegisterWindow.cpp',
    'src/gui/components/wxTitleManagerList.cpp',
]

def remove_wx_translation_wrapper(text):
    """Remove _() wrapper from _(wxString::Format(...)) call sites."""
    result = []
    i = 0
    marker = '_(wxString::Format('
    mlen = len(marker)
    while i < len(text):
        if text[i:i+mlen] == marker:
            j = i + 2
            depth = 1
            while j < len(text) and depth > 0:
                if text[j] == '(':
                    depth += 1
                elif text[j] == ')':
                    depth -= 1
                j += 1
            result.append(text[i+2:j-1])
            i = j
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)

for rel in files_to_patch:
    p = src / rel
    if not p.exists():
        print(f'  skip (not found): {rel}')
        continue
    original = p.read_text()
    text = remove_wx_translation_wrapper(original)
    text = text.replace(
        '_("Collecting list of files..." + fmt::format(" ({})", writerContext.totalFileCount.load()))',
        '_("Collecting list of files...") + fmt::format(" ({})", writerContext.totalFileCount.load())'
    )
    text = text.replace(
        'writerContext.totalFileCount.load())));',
        'writerContext.totalFileCount.load()));'
    )
    if text != original:
        p.write_text(text)
        print(f'  patched: {rel}')
PYEOF

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"
cmake -S "${SRC}" -B "${BUILD}" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=/usr/bin/clang \
    -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
    -DCMAKE_MAKE_PROGRAM=/usr/bin/ninja \
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON \
    -DCMAKE_EXE_LINKER_FLAGS="-fuse-ld=lld -no-pie -lm -lstdc++ -lSPIRV-Tools-opt -lSPIRV-Tools" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="\$ORIGIN/../lib" \
    -DCMAKE_PREFIX_PATH="${WX_PREFIX};${SDL_STACK_ROOT};${HIDAPI_PREFIX}" \
    -DALLOW_PORTABLE=OFF \
    -DBUILD_SHARED_LIBS=OFF \
    -DENABLE_BLUEZ=ON \
    -DENABLE_DISCORD_RPC=OFF \
    -DENABLE_FERAL_GAMEMODE=OFF \
    -DENABLE_HIDAPI=ON \
    -DENABLE_OPENGL=ON \
    -DENABLE_VCPKG=OFF \
    -DENABLE_VULKAN=ON \
    -DENABLE_WAYLAND=ON \
    -DENABLE_WXWIDGETS=ON \
    -DLINUX=ON
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"
found_bin="$(find "${SRC}/bin" "${BUILD}" \
    -maxdepth 3 -type f -perm /111 \
    \( -name 'Cemu_release' -o -name 'Cemu' \) \
    -print -quit 2>/dev/null || true)"
[[ -n "${found_bin}" ]] || die "Cemu binary was not produced"
cp "${found_bin}" "${STAGING}/bin/Cemu"
chmod +x "${STAGING}/bin/Cemu"

mkdir -p "${STAGING}/lib"
for f in /usr/lib/x86_64-linux-gnu/libboost_atomic.so.1.83.0 \
          /usr/lib/x86_64-linux-gnu/libboost_atomic.so.1.83; do
    [[ -f "$f" ]] && cp "$f" "${STAGING}/lib/"
done
(cd "${STAGING}/lib" && ln -sf libboost_atomic.so.1.83.0 libboost_atomic.so.1 2>/dev/null || true)

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
