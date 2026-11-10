#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='drastic'
DOWNLOAD_URL='https://github.com/dmanlfc/drastic/raw/refs/heads/main/drastic.tar.gz'

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
ARCHIVE="${BUILD}/drastic.tar.gz"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

mkdir -p "${BUILD}"
log "Downloading ${DOWNLOAD_URL}"
curl -fL -o "${ARCHIVE}" "${DOWNLOAD_URL}"

rm -rf "${STAGING}" "${BUILD}/extract"
mkdir -p "${STAGING}/bin" "${BUILD}/extract"
tar -xzf "${ARCHIVE}" -C "${BUILD}/extract"
cp -a "${BUILD}/extract/drastic/drastic_aarch64/." "${STAGING}/bin/"
chmod +x "${STAGING}/bin/drastic"

write_artifact_version "${STAGING}" "$(sha256sum "${ARCHIVE}" | cut -c1-12)"
log "Done. Artifact at ${STAGING}"
