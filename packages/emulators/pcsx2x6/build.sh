#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='pcsx2x6'
REPO='https://github.com/PS2Homebrew-arcade/pcsx2x6.git'
TAG="${PCSX2X6_TAG:-$(github_latest_tag "${REPO}")}"
STAGED_BIN='pcsx2x6-qt'
PATCHES_URL='https://github.com/PS2Homebrew-arcade/pcsx2x6_patches/releases/download/latest/patches.zip'

source "/work/packages/emulators/pcsx2/pcsx2-family.sh"

log "Fetching game patches"
mkdir -p "${STAGING}/bin/resources"
curl -fsSL -o "${STAGING}/bin/resources/patches.zip" "${PATCHES_URL}"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
