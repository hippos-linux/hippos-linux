#!/usr/bin/env bash
# Syncs libretro cores from the buildbot nightly.
# Uses ETags to skip cores that haven't changed since last download.
# Use --force to re-download all cores regardless.
set -euo pipefail

source "/work/build/common.sh"

EMULATOR_NAME='retroarch'
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
STAGING_DIR="${ARTIFACT_ROOT}/emulators/${EMULATOR_NAME}"
CORES_DIR="${ARTIFACT_ROOT}/libretro-cores"
ETAG_DIR="${ARTIFACT_ROOT}/libretro-cores/.etags"

BUILDBOT_BASE="https://buildbot.libretro.com/nightly/linux/x86_64/latest"

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

log() { printf '[build:%s] %s\n' "${EMULATOR_NAME}" "$*"; }

mkdir -p "${STAGING_DIR}" "${CORES_DIR}" "${ETAG_DIR}"

log "Fetching buildbot index..."
AVAILABLE=$(curl -fsSL "${BUILDBOT_BASE}/" \
    | grep -o 'href="[^"]*_libretro\.so\.zip"' \
    | sed 's|href="/nightly/linux/x86_64/latest/||;s/\.zip"//' \
    | sort)

total=0
downloaded=0
skipped=0
failed=0

while IFS= read -r so_name; do
    [[ -z "${so_name}" ]] && continue
    total=$(( total + 1 ))

    dest="${CORES_DIR}/${so_name}"
    etag_file="${ETAG_DIR}/${so_name}.etag"

    if [[ "${FORCE}" -eq 0 ]]; then
        remote_etag=$(curl -fsSI "${BUILDBOT_BASE}/${so_name}.zip" \
            | grep -i '^etag:' | tr -d '\r' | awk '{print $2}')
        stored_etag=""
        [[ -f "${etag_file}" ]] && stored_etag=$(cat "${etag_file}")

        if [[ -f "${dest}" && -n "${remote_etag}" && "${remote_etag}" == "${stored_etag}" ]]; then
            skipped=$(( skipped + 1 ))
            continue
        fi
    fi

    log "Downloading ${so_name}..."
    tmp=$(mktemp)
    if curl -fsSL "${BUILDBOT_BASE}/${so_name}.zip" \
            -D "${tmp}.headers" \
            -o "${tmp}"; then
        if unzip -p "${tmp}" "${so_name}" > "${dest}" 2>/dev/null \
            || unzip -p "${tmp}" > "${dest}" 2>/dev/null; then
            # Save ETag for next run
            new_etag=$(grep -i '^etag:' "${tmp}.headers" | tr -d '\r' | awk '{print $2}')
            [[ -n "${new_etag}" ]] && echo -n "${new_etag}" > "${etag_file}"
            downloaded=$(( downloaded + 1 ))
            log "  OK: ${so_name}"
        else
            log "  WARN: could not extract ${so_name}"
            rm -f "${dest}"
            failed=$(( failed + 1 ))
        fi
        rm -f "${tmp}" "${tmp}.headers"
    else
        rm -f "${tmp}" "${tmp}.headers"
        log "  WARN: download failed for ${so_name}"
        failed=$(( failed + 1 ))
    fi
done <<< "${AVAILABLE}"

log "Done — ${total} available, ${downloaded} downloaded, ${skipped} skipped, ${failed} failed"

write_artifact_version "${STAGING_DIR}" "$(date +%Y%m%d)"
