#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='supermodel'
REPO='https://github.com/trzy/Supermodel'
REF="${SUPERMODEL_REF:-master}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${REF}" "${SRC}"

mkdir -p "${STAGING}/bin"

if [[ ! -f "${SRC}/Makefiles/Makefile.UNIX" ]]; then
    die "Makefiles/Makefile.UNIX not found; Supermodel source layout changed"
fi

_cross_args=()
if [[ "${CROSS_BUILD}" -eq 1 ]]; then
    _cross_args=(
        CC="${GNU_ARCH}-gcc"
        CXX="${GNU_ARCH}-g++"
        LD="${GNU_ARCH}-gcc"
        AR="${GNU_ARCH}-ar"
        SDL2_CFLAGS="$("${GNU_ARCH}-pkg-config" --cflags sdl2)"
        SDL2_LIBS="$("${GNU_ARCH}-pkg-config" --libs sdl2 SDL2_net)"
    )
fi

log "Building"
make -C "${SRC}" -f Makefiles/Makefile.UNIX -j"$(nproc)" NET_BOARD=0 "${_cross_args[@]}"

log "Staging binary"
if [[ -x "${SRC}/bin/supermodel" ]]; then
    cp "${SRC}/bin/supermodel" "${STAGING}/bin/supermodel"
else
    found_bin="$(find "${SRC}" -path '*/bin*/supermodel' -type f -perm /111 -print -quit)"
    [[ -n "${found_bin}" ]] || die "supermodel binary was not produced"
    cp "${found_bin}" "${STAGING}/bin/supermodel"
fi

# Stripping is now handled centrally by build/strip-emulator-payload.sh (called from both configure-rootfs.sh and build-emulators.sh).

# Supermodel needs Config/Games.xml to recognise ROM sets, and Assets/ for
# crosshairs; the launcher runs it from a folder that links to these.
rm -rf "${STAGING}/share"
mkdir -p "${STAGING}/share"
cp -r "${SRC}/Config" "${STAGING}/share/Config"
[[ -d "${SRC}/Assets" ]] && cp -r "${SRC}/Assets" "${STAGING}/share/Assets"
[[ -f "${STAGING}/share/Config/Games.xml" ]] || die "Games.xml missing from ${SRC}/Config"

write_artifact_version "${STAGING}" "$(git -C "${SRC}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
