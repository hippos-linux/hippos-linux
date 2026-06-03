#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='redream'
DOWNLOAD_PAGE='https://redream.io/download'

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

mkdir -p "${BUILD}" "${STAGING}/bin"
ARCHIVE="${BUILD}/redream.x86_64-linux-gnu.tar.gz"

if [[ -f "${ARCHIVE}" ]] && ! gzip -t "${ARCHIVE}" >/dev/null 2>&1; then
    log "Discarding invalid cached archive"
    rm -f "${ARCHIVE}"
fi

if [[ ! -f "${ARCHIVE}" ]]; then
    log "Resolving redream Linux download URL"
    REDREAM_FILE="$(curl -sfL 'https://redream.io/download' \
        | grep -o 'redream\.x86_64-linux-v[^"]*\.tar\.gz' | head -1)"
    [[ -n "${REDREAM_FILE}" ]] || die "Could not resolve redream Linux download URL"
    log "Downloading ${REDREAM_FILE}"
    curl -fL "https://redream.io/download/${REDREAM_FILE}" \
        -o "${ARCHIVE}"
fi

tar xf "${ARCHIVE}" -C "${STAGING}/bin" 2>/dev/null || \
    (mkdir -p "${STAGING}/bin" && tar xf "${ARCHIVE}" -C "${STAGING}/bin" --strip-components=1)
chmod +x "${STAGING}/bin/redream" 2>/dev/null || true

write_artifact_version "${STAGING}" "$(date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
