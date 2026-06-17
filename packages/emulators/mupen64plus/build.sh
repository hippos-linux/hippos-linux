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

# mupen64plus Makefiles use CC/LD directly; on arm64 cross-compile the host
# linker (/usr/bin/ld) is x86_64. Pass the cross-toolchain explicitly on the
# make command line so the Makefile can't fall back to native cc/ld.
_cross_args=()
if [[ "${ARCH:-amd64}" == "arm64" ]] && [[ "$(uname -m)" == "x86_64" ]]; then
    _cross_args=(
        CC=aarch64-linux-gnu-gcc
        CXX=aarch64-linux-gnu-g++
        LD=aarch64-linux-gnu-ld
        AR=aarch64-linux-gnu-ar
        CPU=aarch64
        NEW_DYNAREC=1
    )
fi

# Build core first
log "Building mupen64plus-core"
make -C "${SRC}/mupen64plus-core/projects/unix" \
    -j"$(nproc)" \
    all install \
    DESTDIR="${STAGING}" \
    PREFIX=/ \
    "${_cross_args[@]}"

# Build remaining components
for comp in mupen64plus-ui-console mupen64plus-audio-sdl mupen64plus-input-sdl mupen64plus-rsp-hle mupen64plus-video-glide64mk2; do
    log "Building ${comp}"
    make -C "${SRC}/${comp}/projects/unix" \
        -j"$(nproc)" \
        all install \
        DESTDIR="${STAGING}" \
        PREFIX=/ \
        APIDIR="${SRC}/mupen64plus-core/src/api" \
        "${_cross_args[@]}" 2>/dev/null || \
    make -C "${SRC}/${comp}/projects/unix" \
        -j"$(nproc)" \
        all install \
        DESTDIR="${STAGING}" \
        PREFIX=/ \
        "${_cross_args[@]}"
done

write_artifact_version "${STAGING}" "$(date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
