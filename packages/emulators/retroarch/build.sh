#!/usr/bin/env bash
# Use --force to re-download all cores.
set -euo pipefail

source "/work/build/common.sh"

EMULATOR_NAME='retroarch'

# EXCLUDED_CORES: add a core's .so name to leave it out even when retroarch.emulator.yml lists it.
EXCLUDED_CORES=()
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
ETAG_DIR="${ARTIFACT_ROOT}/retroarch-core-etags"

BUILDBOT_BASE="https://buildbot.libretro.com/nightly/linux/${LIBRETRO_ARCH}/latest"

# FREEJ2ME_PLUS_VERSION: FreeJ2ME-Plus release packed with the cores; update the jar SHA256 with it.
FREEJ2ME_PLUS_VERSION='1.53'
FREEJ2ME_PLUS_REPO='https://github.com/TASEmulators/freej2me-plus.git'
FREEJ2ME_PLUS_JAR_URL="https://github.com/TASEmulators/freej2me-plus/releases/download/${FREEJ2ME_PLUS_VERSION}/freej2me_plus-v${FREEJ2ME_PLUS_VERSION}.zip"
FREEJ2ME_PLUS_JAR_SHA256='f2c647c3a62a55d904115fc7ec28103ed3bc3f438cac1de8d90e2cfd4c054f25'
FREEJ2ME_PLUS_SRC="${WORK_ROOT:-/work/work/emulators}/freej2me-plus/source"
FREEJ2ME_PLUS_DIR="${STAGING_DIR}/freej2me"

OPENCDI_REPO='https://github.com/sigsantilio/opencdi'
RETROARCH_REPO='https://github.com/libretro/RetroArch'
RETROARCH_SRC="${WORK_ROOT:-/work/work/emulators}/retroarch/source"
CORE_INFO_URL='https://buildbot.libretro.com/assets/frontend/info.zip'
OPENCDI_SRC="${WORK_ROOT:-/work/work/emulators}/opencdi/source"

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

log() { printf '[build:%s] %s\n' "${EMULATOR_NAME}" "$*"; }

install_freej2me_plus() {
    local tmp stamp="${ETAG_DIR}/freej2me-plus.built"
    if [[ "${FORCE}" -eq 0 && -f "${CORES_DIR}/freej2me_plus_libretro.so" && -f "${FREEJ2ME_PLUS_DIR}/freej2me_plus-lr.jar" \
          && "$(cat "${stamp}" 2>/dev/null)" == "${FREEJ2ME_PLUS_VERSION}" ]]; then
        log "FreeJ2ME-Plus ${FREEJ2ME_PLUS_VERSION} already built"
        return
    fi
    clone_source "${FREEJ2ME_PLUS_REPO}" "${FREEJ2ME_PLUS_VERSION}" "${FREEJ2ME_PLUS_SRC}"
    make -C "${FREEJ2ME_PLUS_SRC}/src/libretro" clean
    make -C "${FREEJ2ME_PLUS_SRC}/src/libretro" -j"$(nproc)"
    install -m755 "${FREEJ2ME_PLUS_SRC}/src/libretro/freej2me_plus_libretro.so" "${CORES_DIR}/freej2me_plus_libretro.so"

    tmp="$(mktemp -d)"
    curl -fsSL "${FREEJ2ME_PLUS_JAR_URL}" -o "${tmp}/jar.zip"
    echo "${FREEJ2ME_PLUS_JAR_SHA256}  ${tmp}/jar.zip" | sha256sum -c --quiet
    mkdir -p "${FREEJ2ME_PLUS_DIR}"
    unzip -p "${tmp}/jar.zip" freej2me_plus-lr.jar > "${FREEJ2ME_PLUS_DIR}/freej2me_plus-lr.jar"
    rm -rf "${tmp}"
    printf '%s\n' "${FREEJ2ME_PLUS_VERSION}" > "${stamp}"
    log "Installed FreeJ2ME-Plus ${FREEJ2ME_PLUS_VERSION}"
}

install_opencdi() {
    local tag stamp="${ETAG_DIR}/opencdi.built"
    tag="$(github_latest_tag "${OPENCDI_REPO}")"
    if [[ "${FORCE}" -eq 0 && -f "${CORES_DIR}/opencdi_libretro.so" && "$(cat "${stamp}" 2>/dev/null)" == "${tag}" ]]; then
        log "OpenCDi ${tag} already built"
        return
    fi
    clone_source "${OPENCDI_REPO}" "${tag}" "${OPENCDI_SRC}"
    cargo build --release --locked --package opencdi-libretro --manifest-path "${OPENCDI_SRC}/Cargo.toml"
    install -m755 "$(cargo_release_dir "${OPENCDI_SRC}")/libopencdi_libretro.so" "${CORES_DIR}/opencdi_libretro.so"
    "${STRIP:-strip}" "${CORES_DIR}/opencdi_libretro.so"
    printf '%s\n' "${tag}" > "${stamp}"
    log "Installed OpenCDi ${tag}"
}

install_retroarch() {
    local tag stamp="${ETAG_DIR}/retroarch.built" filters
    tag="$(github_latest_tag "${RETROARCH_REPO}")"
    if [[ "${FORCE}" -eq 0 && -x "${STAGING_DIR}/bin/retroarch" && "$(cat "${stamp}" 2>/dev/null)" == "${tag}" ]]; then
        log "RetroArch ${tag} already built"
        return
    fi
    clone_source "${RETROARCH_REPO}" "${tag}" "${RETROARCH_SRC}"
    (
        cd "${RETROARCH_SRC}"
        make clean >/dev/null 2>&1 || true
        ./configure --prefix=/usr --disable-qt --disable-jack --disable-v4l2 \
            --disable-update_cores --disable-update_assets --disable-update_core_info
        make -j"$(nproc)"
        make -C libretro-common/audio/dsp_filters clean
        make -C libretro-common/audio/dsp_filters -j"$(nproc)" compiler="${CC:-gcc}"
        make -C gfx/video_filters clean
        make -C gfx/video_filters -j"$(nproc)" compiler="${CC:-gcc}"
    )
    install -Dm755 "${RETROARCH_SRC}/retroarch" "${STAGING_DIR}/bin/retroarch"
    "${STRIP:-strip}" "${STAGING_DIR}/bin/retroarch"
    filters="${STAGING_DIR}/filters"
    rm -rf "${filters}"
    mkdir -p "${filters}/audio" "${filters}/video"
    install -m644 "${RETROARCH_SRC}"/libretro-common/audio/dsp_filters/*.dsp "${filters}/audio/"
    install -m755 "${RETROARCH_SRC}"/libretro-common/audio/dsp_filters/*.so "${filters}/audio/"
    install -m644 "${RETROARCH_SRC}"/gfx/video_filters/*.filt "${filters}/video/"
    install -m755 "${RETROARCH_SRC}"/gfx/video_filters/*.so "${filters}/video/"
    "${STRIP:-strip}" "${filters}"/audio/*.so "${filters}"/video/*.so
    printf '%s\n' "${tag}" > "${stamp}"
    log "Installed RetroArch ${tag}"
}

install_core_info() {
    local tmp
    tmp="$(mktemp -d)"
    curl -fsSL "${CORE_INFO_URL}" -o "${tmp}/info.zip"
    rm -rf "${STAGING_DIR}/info"
    mkdir -p "${STAGING_DIR}/info"
    unzip -q "${tmp}/info.zip" '*.info' -d "${STAGING_DIR}/info"
    rm -rf "${tmp}"
    log "Installed $(find "${STAGING_DIR}/info" -name '*.info' | wc -l) core info files"
}

mkdir -p "${STAGING_DIR}" "${CORES_DIR}" "${ETAG_DIR}"

install_retroarch
install_core_info

log "Fetching buildbot index for ARCH=${ARCH} (${LIBRETRO_ARCH})..."
BUILDBOT_CORES=$(curl -fsSL "${BUILDBOT_BASE}/" \
    | grep -o 'href="[^"]*_libretro\.so\.zip"' \
    | sed 's|href="||;s|\.zip"||' \
    | xargs -n1 basename \
    | LC_ALL=C sort -u)

PACKAGED_CORES=$(python3 - "/work/packages/emulators/${EMULATOR_NAME}/${EMULATOR_NAME}.emulator.yml" "${EXCLUDED_CORES[@]}" <<'PY'
import sys
import yaml
sys.path.insert(0, "/work/overlays/rootfs/usr/lib/hippos")
from libretro_cores import LIBRETRO_CORE_ALIASES, REPLACED_CORES

excluded = set(sys.argv[2:])
packaged = set()
for system in yaml.safe_load(open(sys.argv[1]))["systems"]:
    cores = system.get("as_core") or []
    for core in map(str, cores if isinstance(cores, list) else [cores]):
        core = REPLACED_CORES.get(core, core)
        packaged.update(f"{name}_libretro.so" for name in (core, *LIBRETRO_CORE_ALIASES.get(core, ())))
print("\n".join(sorted(packaged - excluded)))
PY
)

AVAILABLE="$(LC_ALL=C comm -12 <(printf '%s\n' "${BUILDBOT_CORES}") <(printf '%s\n' "${PACKAGED_CORES}"))"
UNPACKAGED="$(LC_ALL=C comm -23 <(printf '%s\n' "${BUILDBOT_CORES}") <(printf '%s\n' "${PACKAGED_CORES}"))"

while IFS= read -r core; do
    if [[ -n "${core}" ]]; then
        rm -f "${CORES_DIR}/${core}" "${ETAG_DIR}/${core}.etag" "${ETAG_DIR}/${core}.build"
    fi
done <<< "${UNPACKAGED}"

report_unpackaged_cores() {
    local report="${ETAG_DIR}/unpackaged-cores.txt"
    [[ "$(cat "${report}" 2>/dev/null)" == "${UNPACKAGED}" ]] && return
    printf '%s\n' "${UNPACKAGED}" > "${report}"
    log "Buildbot cores not packaged: $(tr '\n' ' ' <<< "${UNPACKAGED}")"
    discord_notify grey "RetroArch cores skipped (${ARCH})" \
        "Buildbot cores not in retroarch.emulator.yml (or in EXCLUDED_CORES), so not downloaded:"$'\n'"$(sed 's/_libretro\.so$//' <<< "${UNPACKAGED}" | paste -sd ' ')"
}
report_unpackaged_cores

total=0
downloaded=0
skipped=0
rebuilt=0
failed=0

while IFS= read -r so_name; do
    [[ -z "${so_name}" ]] && continue
    total=$(( total + 1 ))

    dest="${CORES_DIR}/${so_name}"
    etag_file="${ETAG_DIR}/${so_name}.etag"
    build_file="${ETAG_DIR}/${so_name}.build"

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

        if unzip -p "${tmp}" "${so_name}" > "${tmp}.so" 2>/dev/null \
            || unzip -p "${tmp}" > "${tmp}.so" 2>/dev/null; then

            new_etag=$(grep -i '^etag:' "${headers}" | tr -d '\r' | awk '{print $2}' || true)
            [[ -n "${new_etag}" ]] && echo -n "${new_etag}" > "${etag_file}"

            build="$(python3 "/work/packages/emulators/${EMULATOR_NAME}/core-build-identity.py" "${tmp}.so")"
            if [[ -f "${dest}" && "${build}" == "$(cat "${build_file}" 2>/dev/null)" ]]; then
                rebuilt=$(( rebuilt + 1 ))
                log "  same source, keeping the current build: ${so_name}"
            else
                mv "${tmp}.so" "${dest}"
                echo -n "${build}" > "${build_file}"
                downloaded=$(( downloaded + 1 ))
                log "  OK: ${so_name}"
            fi
        else
            log "  WARN: could not extract ${so_name}"
            failed=$(( failed + 1 ))
        fi

        rm -f "${tmp}" "${tmp}.so" "${headers}"
    else
        rm -f "${tmp}" "${headers}"
        log "  WARN: download failed for ${so_name}"
        failed=$(( failed + 1 ))
    fi
done <<< "${AVAILABLE}"

install_freej2me_plus

set +e
( set -e; install_opencdi )
opencdi_status=$?
set -e
if (( opencdi_status != 0 )); then
    log "WARN: OpenCDi build failed (exit ${opencdi_status}); keeping the previous core, if any"
fi

for core in "${CORES_DIR}"/*.so; do
    if readelf -lW "${core}" | grep -q 'GNU_STACK.*RWE'; then
        patchelf --clear-execstack "${core}"
        log "Cleared executable stack: $(basename "${core}")"
    fi
done

log "Done — ${total} available, ${downloaded} updated, ${rebuilt} rebuilt from the same source, ${skipped} unchanged, ${failed} failed"

write_artifact_version "${STAGING_DIR}" "$(content_version "${STAGING_DIR}")"
