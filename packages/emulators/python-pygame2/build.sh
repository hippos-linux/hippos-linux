#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='python-pygame2'

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

mkdir -p "${STAGING}"
log "Installing pygame 2.6.1 via pip"
pip3 install --target="${STAGING}" pygame==2.6.1

write_artifact_version "${STAGING}" "2.6.1"
log "Done. Artifact at ${STAGING}"
