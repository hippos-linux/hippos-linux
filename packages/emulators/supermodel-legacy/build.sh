#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='supermodel-legacy'
REPO='https://github.com/trzy/Supermodel'
TAG="$(github_latest_tag "${REPO}" 2>/dev/null || true)"
if [[ -z "${TAG}" ]]; then
    log "No releases found for ${REPO}; skipping"
    exit 0
fi

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

mkdir -p "${STAGING}/bin"

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

make -C "${SRC}" -f Makefiles/Makefile.UNIX -j"$(nproc)" NET_BOARD=0 "${_cross_args[@]}"

find "${SRC}" -path '*/bin*/supermodel' -type f -perm /111 \
    -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

if [[ ! -x "${STAGING}/bin/supermodel" ]]; then
    die "supermodel-legacy binary was not produced"
fi

# Supermodel needs Config/Games.xml to recognise ROM sets, and Assets/ for
# crosshairs; the launcher runs it from a folder that links to these.
rm -rf "${STAGING}/share"
mkdir -p "${STAGING}/share"
cp -r "${SRC}/Config" "${STAGING}/share/Config"
[[ -d "${SRC}/Assets" ]] && cp -r "${SRC}/Assets" "${STAGING}/share/Assets"
[[ -f "${STAGING}/share/Config/Games.xml" ]] || die "Games.xml missing from ${SRC}/Config"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
