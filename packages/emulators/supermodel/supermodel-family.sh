# Sourced by the build.sh of Supermodel and its forks. Set NAME and SRC (the
# cloned source) before sourcing, then call supermodel_build and
# supermodel_stage <version>.

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
