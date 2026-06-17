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
if [[ "${ARCH:-amd64}" == "arm64" ]] && [[ "$(uname -m)" == "x86_64" ]]; then
    # Makefile.UNIX uses CC/CXX directly and may call sdl2-config (amd64).
    # Override compiler and inject arm64 SDL2 include path so the multiarch
    # SDL_config.h is found instead of the amd64 one.
    _cross_args=(
        CC=aarch64-linux-gnu-gcc
        CXX=aarch64-linux-gnu-g++
        AR=aarch64-linux-gnu-ar
        "CXXFLAGS=-I/usr/include/aarch64-linux-gnu"
        "CFLAGS=-I/usr/include/aarch64-linux-gnu"
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

strip "${STAGING}/bin/supermodel" || true

write_artifact_version "${STAGING}" "$(git -C "${SRC}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
