#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='supermodel'
REPO='https://github.com/trzy/Supermodel'
REF="${SUPERMODEL_REF:-master}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

supermodel_build() {
    local make_args=(NET_BOARD=0)
    if [[ "${CROSS_BUILD}" -eq 1 ]]; then
        local host_m68kmake="${SRC}/m68kmake-host"
        gcc -O2 -o "${host_m68kmake}" "${SRC}/Src/CPU/68K/Musashi/m68kmake.c"
        make_args+=(
            CC="${GNU_ARCH}-gcc"
            CXX="${GNU_ARCH}-g++"
            LD="${GNU_ARCH}-gcc"
            AR="${GNU_ARCH}-ar"
            SDL2_CFLAGS="$("${GNU_ARCH}-pkg-config" --cflags sdl2)"
            SDL2_LIBS="$("${GNU_ARCH}-pkg-config" --libs sdl2 SDL2_net)"
            MUSASHI_OUTFILE="${host_m68kmake}"
        )
    fi
    log "Building"
    make -C "${SRC}" -f Makefiles/Makefile.UNIX -j"$(nproc)" "${make_args[@]}"
}

supermodel_stage() {
    local version="$1" built
    built="$(find "${SRC}" -path '*/bin*/supermodel' -type f -perm /111 -print -quit)"
    [[ -n "${built}" ]] || die "${NAME} binary was not produced"
    rm -rf "${STAGING}"
    mkdir -p "${STAGING}/bin" "${STAGING}/share"
    cp "${built}" "${STAGING}/bin/supermodel"
    cp -r "${SRC}/Config" "${STAGING}/share/Config"
    [[ -d "${SRC}/Assets" ]] && cp -r "${SRC}/Assets" "${STAGING}/share/Assets"
    [[ -f "${STAGING}/share/Config/Games.xml" ]] || die "Games.xml missing from ${SRC}/Config"
    write_artifact_version "${STAGING}" "${version}"
    log "Done. Artifact at ${STAGING}"
}

clone_source "${REPO}" "${REF}" "${SRC}"
[[ -f "${SRC}/Makefiles/Makefile.UNIX" ]] || die "Makefiles/Makefile.UNIX not found; Supermodel source layout changed"

supermodel_build
supermodel_stage "$(git -C "${SRC}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d)"
