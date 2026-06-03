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

# Supermodel's Linux build entrypoint is Makefiles/Makefile.UNIX from the repo
# root. The generated binary lands in bin/supermodel.
make -C "${SRC}" -f Makefiles/Makefile.UNIX -j"$(nproc)" NET_BOARD=0

find "${SRC}" -path '*/bin*/supermodel' -type f -perm /111 \
    -exec cp {} "${STAGING}/bin/" \; 2>/dev/null || true

if [[ ! -x "${STAGING}/bin/supermodel" ]]; then
    die "supermodel-legacy binary was not produced"
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
