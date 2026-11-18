#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='nvidia-legacy'

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
STAGING="${ARTIFACT_ROOT}/${ARCH}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

ARCH="${ARCH:-amd64}"

NVIDIA_LEGACY_TIERS=(
    "580:580.173.02:8d8eb9001e05a9a8a663d3d5d304feb64ef2844ee185ccdfd952786820f46e1b"
    "470:470.256.02:d6451862deb695bb0447f3b7cd6268f73e81168c10e2c10597ff3fa01349b1de"
    "390:390.157:5bebbca6e8fed5d6b9d81070fb9e351f18edc534952553cbdc71e8fd0b9b328a"
    "340:340.108:c671d4f1b7c09bc1af079b98b447adb06d704b04f802f7045a611fa50133b71b"
)

nvidia_legacy_patch_order() {
    case "$1" in
        580)
            printf '%s\n' \
                0001-use-LDFLAGS.patch \
                0002-fix-linux-7.2-strncpy-removal.patch
            ;;
        470)
            printf '%s\n' \
                0001-Fix-conftest-to-ignore-implicit-function-declaration.patch \
                0002-Fix-conftest-to-use-a-short-wchar_t.patch \
                0003-Fix-conftest-to-use-nv_drm_gem_vmap-which-has-the-se.patch \
                kernel-6.10.patch \
                kernel-6.12.patch \
                nvidia-470xx-fix-gcc-15.patch \
                nvidia-470xx-fix-linux-6.13.patch \
                nvidia-470xx-fix-linux-6.14.patch \
                nvidia-470xx-fix-linux-6.15.patch \
                nvidia-470xx-fix-linux-6.17.patch \
                nvidia-470xx-fix-linux-6.19-part1.patch \
                nvidia-470xx-fix-linux-6.19-part2.patch \
                nvidia-470xx-fix-linux-7.0.patch \
                nvidia-470xx-fix-linux-7.2-part1.patch \
                nvidia-470xx-fix-linux-7.2-part2.patch \
                nvidia-470xx-fix-linux-7.2-part3.patch \
                nvidia-470xx-fix-linux-7.3.patch \
                nvidia-470xx-fix-linux-7.4.patch \
                nvidia-470xx-fix-clang.patch \
                disable-objtool-override.patch \
                enable-drm-modeset-by-default.patch \
                nvidia-470xx-fix-linux-6.15-followup.patch
            ;;
        390)
            printf '%s\n' \
                kernel-4.16+-memory-encryption.patch \
                kernel-6.2.patch \
                kernel-6.3.patch \
                kernel-6.4.patch \
                kernel-6.5.patch \
                kernel-6.6.patch \
                kernel-6.8.patch \
                gcc-14.patch \
                kernel-6.10.patch \
                kernel-6.12.patch \
                kernel-6.13.patch \
                kernel-6.14.patch \
                gcc-15.patch \
                kernel-6.15.patch \
                kernel-6.17.patch \
                kernel-6.19.patch \
                kernel-6.18-nv_workqueue_flush.patch \
                kernel-7.0.patch \
                kernel-7.2.patch \
                kernel-7.3.patch
            ;;
        340)
            (cd "${REPO_ROOT}/build/patches/nvidia-legacy/340" 2>/dev/null && ls -1 *.patch 2>/dev/null | sort)
            ;;
    esac
}

nvidia_legacy_patch_apply_dir() {
    case "$1" in
        470) printf 'kernel' ;;
        *)   printf '.' ;;
    esac
}

apply_nvidia_legacy_patches() {
    local tier="$1" extract_dir="$2"
    local patch_dir="${REPO_ROOT}/build/patches/nvidia-legacy/${tier}"
    [[ -d "${patch_dir}" ]] || return 0
    local apply_dir="${extract_dir}/$(nvidia_legacy_patch_apply_dir "${tier}")"
    local patch_file applied=0
    while IFS= read -r patch_file; do
        [[ -n "${patch_file}" ]] || continue
        [[ -f "${patch_dir}/${patch_file}" ]] || { log "WARNING: missing vendored patch ${patch_file} for tier ${tier}"; continue; }
        if patch -Np1 -d "${apply_dir}" --silent < "${patch_dir}/${patch_file}"; then
            applied=$((applied + 1))
        else
            log "WARNING: ${patch_file} failed to apply for tier ${tier} — driver source may not build against a kernel this new"
        fi
    done < <(nvidia_legacy_patch_order "${tier}")
    log "  Applied ${applied} kernel-compat patch(es) for tier ${tier}"
}

mkdir -p "${STAGING}/usr/lib/x86_64-linux-gnu/vdpau" \
         "${STAGING}/usr/lib/xorg/modules/drivers" \
         "${STAGING}/usr/lib/xorg/modules/extensions" \
         "${STAGING}/usr/share/vulkan/icd.d" \
         "${STAGING}/usr/share/nvidia/modules"

BUILT_ANY=0

STATUS_FILE="${WORK_ROOT}/${NAME}/.tier-status"
declare -A TIER_BUILT_PREV=()
if [[ -f "${STATUS_FILE}" ]]; then
    while read -r _tier _status; do
        [[ -n "${_tier}" ]] && TIER_BUILT_PREV["${_tier}"]="${_status}"
    done < "${STATUS_FILE}"
fi
declare -A TIER_BUILT_THIS_RUN=()

for entry in "${NVIDIA_LEGACY_TIERS[@]}"; do
    tier="${entry%%:*}"
    rest="${entry#*:}"
    version="${rest%%:*}"
    expected_sha256="${rest#*:}"

    log "Fetching NVIDIA legacy driver ${version} (tier ${tier})"
    RUN_CACHE="${CACHE_DIR}/NVIDIA-Linux-x86_64-${version}.run"
    if [[ ! -f "${RUN_CACHE}" ]]; then
        curl -fsSL --max-time 600 -o "${RUN_CACHE}.tmp" \
            "https://us.download.nvidia.com/XFree86/Linux-x86_64/${version}/NVIDIA-Linux-x86_64-${version}.run" \
            || { log "WARNING: download failed for NVIDIA ${version} — skipping tier ${tier}"; rm -f "${RUN_CACHE}.tmp"; continue; }
        mv "${RUN_CACHE}.tmp" "${RUN_CACHE}"
    fi
    actual_sha256="$(sha256sum "${RUN_CACHE}" | awk '{print $1}')"
    if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
        log "WARNING: checksum mismatch for NVIDIA ${version} (got ${actual_sha256}) — skipping tier ${tier}"
        continue
    fi

    EXTRACT_DIR="${WORK_ROOT}/${NAME}/extract-${tier}"
    rm -rf "${EXTRACT_DIR}"
    chmod +x "${RUN_CACHE}"
    "${RUN_CACHE}" --extract-only --target "${EXTRACT_DIR}"

    log "  Applying kernel-compat patches for tier ${tier}"
    apply_nvidia_legacy_patches "${tier}" "${EXTRACT_DIR}"

    if [[ -f "${EXTRACT_DIR}/kernel/Kbuild" ]]; then
        sed -i '/^EXTRA_CFLAGS += -DNV_KERNEL_INTERFACE_LAYER$/a\
ccflags-y += $(EXTRA_CFLAGS)' "${EXTRACT_DIR}/kernel/Kbuild"
    elif [[ -f "${EXTRACT_DIR}/kernel/nvidia-modules-common.mk" ]]; then
        printf '\nccflags-y += $(EXTRA_CFLAGS)\n' >> "${EXTRACT_DIR}/kernel/nvidia-modules-common.mk"
    fi

    log "Staging tier ${tier} userspace libraries"
    for lib in "${EXTRACT_DIR}/libGLX_nvidia.so.${version}" "${EXTRACT_DIR}/libEGL_nvidia.so.${version}" \
               "${EXTRACT_DIR}/libGLESv1_CM_nvidia.so.${version}" "${EXTRACT_DIR}/libGLESv2_nvidia.so.${version}" \
               "${EXTRACT_DIR}/libnvidia-glcore.so.${version}" "${EXTRACT_DIR}/libnvidia-eglcore.so.${version}" \
               "${EXTRACT_DIR}/libnvidia-glsi.so.${version}" "${EXTRACT_DIR}/libnvidia-tls.so.${version}" \
               "${EXTRACT_DIR}/libnvidia-cfg.so.${version}" "${EXTRACT_DIR}/libnvidia-ml.so.${version}" \
               "${EXTRACT_DIR}/libnvidia-allocator.so.${version}"; do
        [[ -f "${lib}" ]] || continue
        cp "${lib}" "${STAGING}/usr/lib/x86_64-linux-gnu/$(basename "${lib}")"
    done
    _vdpau="${EXTRACT_DIR}/libvdpau_nvidia.so.${version}"
    [[ -f "${_vdpau}" ]] && cp "${_vdpau}" "${STAGING}/usr/lib/x86_64-linux-gnu/vdpau/$(basename "${_vdpau}")"

    [[ -f "${EXTRACT_DIR}/nvidia_drv.so" ]] && \
        cp "${EXTRACT_DIR}/nvidia_drv.so" "${STAGING}/usr/lib/xorg/modules/drivers/nvidia${tier}legacy_drv.so"
    _glxserver="${EXTRACT_DIR}/libglxserver_nvidia.so.${version}"
    [[ -f "${_glxserver}" ]] && cp "${_glxserver}" "${STAGING}/usr/lib/xorg/modules/extensions/$(basename "${_glxserver}")"

    if [[ -f "${EXTRACT_DIR}/nvidia_icd.json" ]]; then
        sed "s|\"library_path\": *\"libGLX_nvidia|\"library_path\": \"/usr/lib/x86_64-linux-gnu/libGLX_nvidia|" \
            "${EXTRACT_DIR}/nvidia_icd.json" > "${STAGING}/usr/share/vulkan/icd.d/nvidia${tier}_legacy_icd.json"
    fi

    log "Building tier ${tier} kernel modules"
    _built_any_release=0
    for variant in standard lts; do
        KERNEL_ARTIFACTS_DIR="${ARTIFACT_ROOT}/${ARCH}/kernel/${variant}"
        HEADERS_DEB="$(ls "${KERNEL_ARTIFACTS_DIR}"/linux-headers-*.deb 2>/dev/null | head -1)"
        if [[ -z "${HEADERS_DEB}" ]]; then
            if [[ "${variant}" == "standard" ]]; then
                log "No kernel headers artifact at ${KERNEL_ARTIFACTS_DIR} — run build/build-kernel.sh first"
            else
                log "No lts headers artifact — skipping lts for tier ${tier}"
            fi
            continue
        fi

        HEADERS_ROOT="${WORK_ROOT}/${NAME}/headers-${variant}"
        rm -rf "${HEADERS_ROOT}"
        mkdir -p "${HEADERS_ROOT}"
        dpkg-deb -x "${HEADERS_DEB}" "${HEADERS_ROOT}"
        KERNEL_SOURCE_DIR="$(find "${HEADERS_ROOT}/usr/src" -maxdepth 1 -type d -name 'linux-headers-*' | head -1)"
        [[ -n "${KERNEL_SOURCE_DIR}" ]] || { log "Couldn't find extracted headers under ${HEADERS_ROOT}/usr/src"; continue; }
        KVER="$(basename "${KERNEL_SOURCE_DIR}")"
        KVER="${KVER#linux-headers-}"

        log "  Building tier ${tier} kernel modules against ${KVER} (${variant})"
        make -C "${EXTRACT_DIR}/kernel" clean >/dev/null 2>&1 || true
        if ARCH=x86_64 make -C "${EXTRACT_DIR}/kernel" \
                SYSSRC="${KERNEL_SOURCE_DIR}" \
                SYSOUT="${KERNEL_SOURCE_DIR}" \
                NV_KERNEL_MODULES="nvidia nvidia-modeset nvidia-drm nvidia-uvm" \
                IGNORE_CC_MISMATCH=1 module; then
            declare -A _legacy_modmap=(
                [nvidia]="nvidia${tier}-legacy.ko"
                [nvidia-modeset]="nvidia${tier}-modeset-legacy.ko"
                [nvidia-drm]="nvidia${tier}-drm-legacy.ko"
                [nvidia-uvm]="nvidia${tier}-uvm-legacy.ko"
            )
            mkdir -p "${STAGING}/usr/share/nvidia/modules/${KVER}"
            for mod in "${!_legacy_modmap[@]}"; do
                _built="${EXTRACT_DIR}/kernel/${mod}.ko"
                [[ -f "${_built}" ]] && cp "${_built}" \
                    "${STAGING}/usr/share/nvidia/modules/${KVER}/${_legacy_modmap[${mod}]}"
            done
            unset _legacy_modmap
            _built_any_release=1
            BUILT_ANY=1
        else
            log "WARNING: kernel module build failed for NVIDIA ${version} (tier ${tier}, kernel ${KVER})"
        fi
    done

    [[ "${_built_any_release}" -eq 1 ]] && echo "${version}" > "${STAGING}/usr/share/nvidia/legacy${tier}.version"
    TIER_BUILT_THIS_RUN["${tier}"]="${_built_any_release}"

    rm -rf "${EXTRACT_DIR}"
done

[[ "${BUILT_ANY}" -eq 1 ]] || log "WARNING: no legacy NVIDIA tier produced a working kernel module — older GPUs will fall back to nouveau"

regressed=()
for tier in "${!TIER_BUILT_PREV[@]}"; do
    if [[ "${TIER_BUILT_PREV[${tier}]}" == "1" && "${TIER_BUILT_THIS_RUN[${tier}]:-0}" != "1" ]]; then
        regressed+=("${tier}")
    fi
done

if [[ "${#regressed[@]}" -gt 0 ]]; then
    die "NVIDIA legacy tier(s) regressed — built successfully last run, failed this run: ${regressed[*]}. Not updating ${STATUS_FILE} — fix the regression (or, if it's now expected to be permanently broken like tier 340, edit ${STATUS_FILE} by hand) before re-running."
fi

mkdir -p "$(dirname "${STATUS_FILE}")"
: > "${STATUS_FILE}"
for tier in "${!TIER_BUILT_THIS_RUN[@]}"; do
    echo "${tier} ${TIER_BUILT_THIS_RUN[${tier}]}" >> "${STATUS_FILE}"
done

log "Done. Artifact at ${STAGING}"
