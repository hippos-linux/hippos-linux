#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='windowsarcadeloader'
REPO='https://github.com/aderumier/windowsarcadeloader.git'
TAG="${WINDOWSARCADELOADER_TAG:-$(github_latest_tag "${REPO}")}"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

log "Building ${TAG}"
rm -rf "${SRC}/dist"
"${SRC}/build.sh"

rm -rf "${STAGING}"
mkdir -p "${STAGING}"
cp "${SRC}/dist/arcade-launcher" "${STAGING}/"
cp -r "${SRC}/dist/payloads" "${SRC}/systemprofiles" "${STAGING}/"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
