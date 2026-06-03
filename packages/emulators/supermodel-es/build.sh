#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='supermodel-es'
REPO='https://github.com/rtissera/Supermodel'

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} (default branch — no releases)"
    rm -rf "${SRC}"
    GIT_TERMINAL_PROMPT=0 git -c credential.helper= clone --depth=1 "${REPO}" "${SRC}"
fi

mkdir -p "${STAGING}/bin"

# Supermodel's Linux build entrypoint is Makefiles/Makefile.UNIX from the repo
# root. The generated binary lands in bin/supermodel.
make -C "${SRC}" -f Makefiles/Makefile.UNIX -j"$(nproc)" NET_BOARD=0

find "${SRC}" -path '*/bin*/supermodel' -type f -perm /111 \
    -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

if [[ ! -x "${STAGING}/bin/supermodel" ]]; then
    die "supermodel-es binary was not produced"
fi

VERSION="$(git -C "${SRC}" rev-parse --short HEAD)"
write_artifact_version "${STAGING}" "${VERSION}"
log "Done. Artifact at ${STAGING}"
