#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='armsx2'
REPO='https://github.com/ARMSX2/ARMSX2.git'
TAG="${ARMSX2_TAG:-$(github_latest_tag "${REPO}")}"
STAGED_BIN='armsx2-qt'
BUILT_BIN='armsx2-qt'
EXTRA_CMAKE_ARGS=(-DHOST_PAGE_SIZE=4096 -DHOST_CACHE_LINE_SIZE=64)
PATCHES_URL='https://github.com/PCSX2/pcsx2_patches/releases/download/latest/patches.zip'

source "/work/packages/emulators/pcsx2/pcsx2-family.sh"

log "Fetching game patches"
mkdir -p "${STAGING}/bin/resources"
curl -fsSL -o "${STAGING}/bin/resources/patches.zip" "${PATCHES_URL}"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
