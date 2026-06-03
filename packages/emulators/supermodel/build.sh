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

log "Building"
make -C "${SRC}" -f Makefiles/Makefile.UNIX -j"$(nproc)" NET_BOARD=0

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
