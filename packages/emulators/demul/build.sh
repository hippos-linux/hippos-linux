#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='demul'
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="${PACKAGE_DIR}/demul-0.7-20251211.tar.xz"
PAYLOAD_SHA256='49ce97c3e3b0f4dcf9cf33b2060b265177225939c4d5598bf334c591f07c8198'

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

echo "${PAYLOAD_SHA256}  ${PAYLOAD}" | sha256sum -c -

rm -rf "${STAGING}"
mkdir -p "${STAGING}"
tar -xJf "${PAYLOAD}" -C "${STAGING}" --no-same-owner

write_artifact_version "${STAGING}" "0.7-20251211"
log "Done. Artifact at ${STAGING}"
