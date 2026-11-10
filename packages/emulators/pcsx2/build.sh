#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='pcsx2'
REPO='https://github.com/pcsx2/pcsx2.git'
TAG="${PCSX2_TAG:-$(github_latest_tag "${REPO}")}"
STAGED_BIN='pcsx2-qt'

source "/work/packages/emulators/pcsx2/pcsx2-family.sh"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
