#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='vice'
VERSION="$(curl -sf 'https://sourceforge.net/projects/vice-emu/files/releases/' \
    | grep -oP 'vice-\K[0-9]+\.[0-9]+(?=\.tar)' | sort -V | tail -1)"
TARBALL_URL="https://sourceforge.net/projects/vice-emu/files/releases/vice-${VERSION}.tar.gz/download"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -d "${SRC}" ]] || [[ -z "$(ls -A "${SRC}" 2>/dev/null)" ]]; then
    log "Downloading vice-${VERSION}.tar.gz"
    mkdir -p "${BUILD}"
    curl -L "${TARBALL_URL}" -o "${BUILD}/vice-${VERSION}.tar.gz"
    mkdir -p "${SRC}"
    tar xf "${BUILD}/vice-${VERSION}.tar.gz" -C "${SRC}" --strip-components=1
fi

mkdir -p "${STAGING}/bin"
(
    cd "${SRC}"
    autoreconf -i
    ./configure \
        --prefix="${STAGING}" \
        --enable-sdlui2 \
        --without-oss

    # GCC 10+ changed -fno-common default; old VICE has z80_regs as a tentative global
    # in both cpmcart.c and z80.c, causing a multiple-definition linker error in x128.
    find "${SRC}/src" -name 'Makefile' -exec sed -i 's/^CFLAGS = /CFLAGS = -fcommon /' {} \;

    make -j"$(nproc)"
    make install
)

write_artifact_version "${STAGING}" "${VERSION}"
log "Done. Artifact at ${STAGING}"
