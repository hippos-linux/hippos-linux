#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='mupen64plus'
BASE_URL='https://github.com/mupen64plus'

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

COMPONENTS=(
    mupen64plus-core
    mupen64plus-ui-console
    mupen64plus-audio-sdl
    mupen64plus-input-sdl
    mupen64plus-rsp-hle
    mupen64plus-video-glide64mk2
)

mkdir -p "${SRC}" "${STAGING}"

for comp in "${COMPONENTS[@]}"; do
    comp_src="${SRC}/${comp}"
    if [[ ! -d "${comp_src}/.git" ]]; then
        log "Cloning ${comp}"
        GIT_TERMINAL_PROMPT=0 git -c credential.helper= clone --depth=1 "${BASE_URL}/${comp}.git" "${comp_src}"
    fi
done

_make_args=(INSTALL_STRIP_FLAG=)
if [[ "${CROSS_BUILD}" -eq 1 ]]; then
    _make_args+=(
        CC="${GNU_ARCH}-gcc"
        CXX="${GNU_ARCH}-g++"
        LD="${GNU_ARCH}-ld"
        AR="${GNU_ARCH}-ar"
        HOST_CPU=aarch64
        NEW_DYNAREC=1
    )
fi

for comp in "${COMPONENTS[@]}"; do
    make -C "${SRC}/${comp}/projects/unix" clean "${_make_args[@]}" >/dev/null
done

log "Building mupen64plus-core"
make -C "${SRC}/mupen64plus-core/projects/unix" \
    -j"$(nproc)" \
    all install \
    DESTDIR="${STAGING}" \
    PREFIX=/ \
    "${_make_args[@]}"

# Build remaining components
for comp in mupen64plus-ui-console mupen64plus-audio-sdl mupen64plus-input-sdl mupen64plus-rsp-hle mupen64plus-video-glide64mk2; do
    log "Building ${comp}"
    make -C "${SRC}/${comp}/projects/unix" \
        -j"$(nproc)" \
        all install \
        DESTDIR="${STAGING}" \
        PREFIX=/ \
        APIDIR="${SRC}/mupen64plus-core/src/api" \
        "${_make_args[@]}" 2>/dev/null || \
    make -C "${SRC}/${comp}/projects/unix" \
        -j"$(nproc)" \
        all install \
        DESTDIR="${STAGING}" \
        PREFIX=/ \
        "${_make_args[@]}"
done

write_artifact_version "${STAGING}" "$(date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
