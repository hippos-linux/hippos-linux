#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='gamescope'
REPO='https://github.com/ValveSoftware/gamescope.git'
TAG="${GAMESCOPE_TAG:-$(github_latest_tag "${REPO}")}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${TAG}"
    git clone --depth=1 --branch "${TAG}" --recurse-submodules "${REPO}" "${SRC}"
fi

log "Configuring with meson"
mkdir -p "${BUILD}" "${STAGING}/bin"

# Debian's xwayland package provides no xwayland.pc; wlroots' bundled meson.build
# calls dependency('xwayland', fallback: ['xserver', ...]) and fails when the pkg
# isn't found and the xserver subproject doesn't exist. Synthesise a minimal .pc.
if ! pkg-config --exists xwayland 2>/dev/null; then
    _XW_VERSION=$(dpkg-query -W -f='${Version}' xwayland 2>/dev/null | grep -oP '^\d+\.\d+' || echo '23.2')
    mkdir -p /usr/local/lib/pkgconfig
    cat > /usr/local/lib/pkgconfig/xwayland.pc << EOF
Name: xwayland
Description: Xwayland X server bridge for Wayland compositors
Version: ${_XW_VERSION}
prefix=/usr
bindir=\${prefix}/bin
Requires: xcb xcb-composite xcb-xfixes xcb-render
Cflags:
Libs:
EOF
fi

if [[ -f "${BUILD}/build.ninja" ]]; then
    meson setup --reconfigure "${BUILD}" "${SRC}" \
        --buildtype=release \
        --prefix=/usr
else
    meson setup "${BUILD}" "${SRC}" \
        --buildtype=release \
        --prefix=/usr
fi

log "Building"
ninja -C "${BUILD}" -j"$(nproc)"

log "Staging binary"
cp "${BUILD}/src/gamescope" "${STAGING}/bin/gamescope"
strip "${STAGING}/bin/gamescope"

log "Done. Artifact at ${STAGING}"
