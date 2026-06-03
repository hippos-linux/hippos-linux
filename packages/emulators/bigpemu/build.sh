#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='bigpemu'

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

mkdir -p "${BUILD}" "${STAGING}/bin"

ARCHIVE="${BUILD}/BigPEMU_Linux.tar.gz"

if [[ -f "${ARCHIVE}" ]] && ! gzip -t "${ARCHIVE}" >/dev/null 2>&1; then
    log "Discarding invalid cached archive"
    rm -f "${ARCHIVE}"
fi

if [[ ! -f "${ARCHIVE}" ]]; then
    log "Resolving BigPEmu Linux download URL"

    BIGPEMU_FILE="$(curl -sfL \
        -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' \
        -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' \
        -H 'Accept-Language: en-US,en;q=0.5' \
        'https://www.richwhitehouse.com/jaguar/index.php?content=download' \
        | grep -oi 'BigPEmu_Linux64_v[0-9]*\.tar\.gz' \
        | head -1)"

    [[ -n "${BIGPEMU_FILE}" ]] || die "Could not resolve BigPEmu Linux download URL"

    log "Downloading ${BIGPEMU_FILE}"
    curl -fL \
        -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' \
        -H 'Accept: application/octet-stream,*/*;q=0.9' \
        -H 'Accept-Language: en-US,en;q=0.5' \
        "https://www.richwhitehouse.com/jaguar/builds/${BIGPEMU_FILE}" \
        -o "${ARCHIVE}"
fi

tar xf "${ARCHIVE}" -C "${STAGING}/bin" --strip-components=1 2>/dev/null || \
    tar xf "${ARCHIVE}" -C "${STAGING}/bin"
chmod +x "${STAGING}/bin/BigPEMU" 2>/dev/null || true

write_artifact_version "${STAGING}" "$(date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
