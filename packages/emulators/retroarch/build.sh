#!/usr/bin/env bash
# Syncs libretro cores from the buildbot nightly into the retroarch package.
# Uses ETags to skip cores that haven't changed since last download.
# Use --force to re-download all cores regardless.
set -euo pipefail

source "/work/build/common.sh"

EMULATOR_NAME='retroarch'

# EXCLUDED_CORES: buildbot cores left out of the package; add a core's .so name to drop it.
EXCLUDED_CORES=(
    qemu_libretro.so hbmame_libretro.so linuxloader_libretro.so dosbox_libretro.so
    nicaiemu_libretro.so pcem_libretro.so chailove_libretro.so mcsoftserve_libretro.so
    romcleaner_libretro.so 3dengine_libretro.so pocketcdg_libretro.so radio_libretro.so
    pokketstation_libretro.so remotejoy_libretro.so oberon_libretro.so video_processor_libretro.so
    rpcs3_libretro.so xemu_libretro.so xenia_edge_libretro.so vita3k_libretro.so
    citra_libretro.so citra2018_libretro.so panda3ds_libretro.so play_libretro.so pcee2_libretro.so
    mame2015_libretro.so mame2016_libretro.so parallel_dc_libretro.so rust_dos_libretro.so
    uzdoom_libretro.so n64emu_libretro.so
)
case "${ARCH}" in
    amd64)
        LIBRETRO_ARCH="x86_64"
        EXCLUDED_CORES+=(cemu_libretro.so)
        ;;
    arm64)
        LIBRETRO_ARCH="aarch64"
        ;;
    *)
        die "Unsupported libretro buildbot arch for ARCH=${ARCH}"
        ;;
esac

ARTIFACT_ROOT="${ARTIFACT_ROOT:-"${ARTIFACTS_DIR}/${ARCH}"}"
STAGING_DIR="${ARTIFACT_ROOT}/emulators/${EMULATOR_NAME}"
CORES_DIR="${STAGING_DIR}/cores"
# Outside the staging dir so the ETags are not packed with the cores.
ETAG_DIR="${ARTIFACT_ROOT}/retroarch-core-etags"

BUILDBOT_BASE="https://buildbot.libretro.com/nightly/linux/${LIBRETRO_ARCH}/latest"

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

log() { printf '[build:%s] %s\n' "${EMULATOR_NAME}" "$*"; }

mkdir -p "${STAGING_DIR}" "${CORES_DIR}" "${ETAG_DIR}"

log "Fetching buildbot index for ARCH=${ARCH} (${LIBRETRO_ARCH})..."
AVAILABLE=$(curl -fsSL "${BUILDBOT_BASE}/" \
    | grep -o 'href="[^"]*_libretro\.so\.zip"' \
    | sed 's|href="||;s|\.zip"||' \
    | xargs -n1 basename \
    | sort)

for core in "${EXCLUDED_CORES[@]}"; do
    AVAILABLE="$(grep -vxF "${core}" <<< "${AVAILABLE}" || true)"
    rm -f "${CORES_DIR}/${core}" "${ETAG_DIR}/${core}.etag"
done

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
            | grep -i '^etag:' | tr -d '\r' | awk '{print $2}' || true)

        stored_etag=""
        [[ -f "${etag_file}" ]] && stored_etag=$(cat "${etag_file}")

        if [[ -f "${dest}" && -n "${remote_etag}" && "${remote_etag}" == "${stored_etag}" ]]; then
            skipped=$(( skipped + 1 ))
            continue
        fi
    fi

    log "Downloading ${so_name}..."

    tmp="$(mktemp)"
    headers="${tmp}.headers"

    if curl -fsSL "${BUILDBOT_BASE}/${so_name}.zip" \
            -D "${headers}" \
            -o "${tmp}"; then

        if unzip -p "${tmp}" "${so_name}" > "${dest}" 2>/dev/null \
            || unzip -p "${tmp}" > "${dest}" 2>/dev/null; then

            new_etag=$(grep -i '^etag:' "${headers}" | tr -d '\r' | awk '{print $2}' || true)
            [[ -n "${new_etag}" ]] && echo -n "${new_etag}" > "${etag_file}"

            downloaded=$(( downloaded + 1 ))
            log "  OK: ${so_name}"
        else
            log "  WARN: could not extract ${so_name}"
            rm -f "${dest}"
            failed=$(( failed + 1 ))
        fi

        rm -f "${tmp}" "${headers}"
    else
        rm -f "${tmp}" "${headers}"
        log "  WARN: download failed for ${so_name}"
        failed=$(( failed + 1 ))
    fi
done <<< "${AVAILABLE}"

# glibc 2.41 refuses to load a library that asks for an executable stack, and a
# couple of buildbot cores do. RetroArch reports only "Failed to open libretro core".
for core in "${CORES_DIR}"/*.so; do
    if readelf -lW "${core}" | grep -q 'GNU_STACK.*RWE'; then
        patchelf --clear-execstack "${core}"
        log "Cleared executable stack: $(basename "${core}")"
    fi
done

log "Done — ${total} available, ${downloaded} downloaded, ${skipped} skipped, ${failed} failed"

write_artifact_version "${STAGING_DIR}" "$(date +%Y%m%d)"
