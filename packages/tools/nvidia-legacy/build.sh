#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='nvidia-legacy'

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
STAGING="${ARTIFACT_ROOT}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

ARCH="${ARCH:-amd64}"

# nvidia-open (installed separately via apt in configure-rootfs.sh) only
# binds Turing/RTX 20xx and newer. These three tiers cover everything older
# — Debian doesn't package any legacy branch for Trixie at all (checked live
# against packages.debian.org), so these come straight from NVIDIA's own
# official .run installers, the same distribution channel nvidia-open itself
# uses upstream.
#
# Every tier's userspace .so keeps its full version suffix and every tier's
# kernel module is staged under a tier-prefixed name, so nothing here ever
# collides with nvidia-open's files or another tier's. hippos-gpu-init is the
# only thing that switches between them at boot — see that script.
NVIDIA_LEGACY_TIERS=(
    "470:470.256.02:d6451862deb695bb0447f3b7cd6268f73e81168c10e2c10597ff3fa01349b1de"
    "390:390.157:5bebbca6e8fed5d6b9d81070fb9e351f18edc534952553cbdc71e8fd0b9b328a"
    "340:340.108:c671d4f1b7c09bc1af079b98b447adb06d704b04f802f7045a611fa50133b71b"
)

mkdir -p "${STAGING}/usr/lib/x86_64-linux-gnu/vdpau" \
         "${STAGING}/usr/lib/xorg/modules/drivers" \
         "${STAGING}/usr/lib/xorg/modules/extensions" \
         "${STAGING}/usr/share/vulkan/icd.d" \
         "${STAGING}/usr/share/nvidia/modules"

_sgpu_json_installed=0
BUILT_ANY=0

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

    # kernel/Kbuild accumulates every module's -I/-D flags into EXTRA_CFLAGS
    # (used since pre-2.6.24) and its own comment claims "newer kernels
    # append $(EXTRA_CFLAGS) to ccflags-y for compatibility" — that
    # compat shim no longer exists anywhere in current mainline kbuild, so
    # EXTRA_CFLAGS silently never reaches the real per-object compile.
    # Confirmed by direct iteration: this alone was the root cause of three
    # separate-looking failures — nvmisc.h not found (needs
    # -I$(src)/common/inc), stdarg.h not found (nv_stdarg.h's correct
    # <linux/stdarg.h> path is gated behind -DNV_KERNEL_INTERFACE_LAYER),
    # and bogus uint32_t/stdint.h errors (nv-ioctl-numa.h's correct
    # <linux/types.h> path is gated behind the same macro). Forwarding
    # EXTRA_CFLAGS into ccflags-y (kbuild's actual always-applied
    # mechanism) fixes all three at once, and is the fix NVIDIA's own
    # comment already describes as the intended behavior.
    sed -i '/^EXTRA_CFLAGS += -DNV_KERNEL_INTERFACE_LAYER$/a\
ccflags-y += $(EXTRA_CFLAGS)' "${EXTRACT_DIR}/kernel/Kbuild"

    if [[ "${_sgpu_json_installed}" -eq 0 && -f "${EXTRACT_DIR}/supported-gpus/supported-gpus.json" ]]; then
        # Cumulative device database bundled in every NVIDIA .run installer
        # (RIVA TNT through RTX 50-series in the copy this was verified
        # against) — not version-specific, any tier's copy works.
        cp "${EXTRACT_DIR}/supported-gpus/supported-gpus.json" "${STAGING}/usr/share/nvidia/supported-gpus.json"
        _sgpu_json_installed=1
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

    # Xorg driver + GLX extension module — tier-prefixed filenames so they
    # never collide with nvidia-open's or each other's.
    [[ -f "${EXTRACT_DIR}/nvidia_drv.so" ]] && \
        cp "${EXTRACT_DIR}/nvidia_drv.so" "${STAGING}/usr/lib/xorg/modules/drivers/nvidia${tier}_legacy_drv.so"
    _glxserver="${EXTRACT_DIR}/libglxserver_nvidia.so.${version}"
    [[ -f "${_glxserver}" ]] && cp "${_glxserver}" "${STAGING}/usr/lib/xorg/modules/extensions/$(basename "${_glxserver}")"

    # Vulkan ICD — 340.xx predates Vulkan entirely, nvidia_icd.json just
    # won't exist there, nothing to stage, that's correct.
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
        # ARCH=x86_64 explicit on the make command line — same fix as
        # build-kernel.sh's MAKE_KERNEL_ARGS. The kernel source tree names
        # its arch dir "x86"/"x86_64" (kernel convention), not "amd64"
        # (Debian's, and this build image's default $ARCH); kbuild trusts
        # whatever ARCH it's given and looks for a nonexistent
        # arch/amd64/Makefile otherwise. nvidia-installer normalizes this
        # internally when run in full, but calling `make` directly here
        # bypasses that.
        #
        # NV_KERNEL_MODULES lists which per-module Kbuild fragments to build
        # (nvidia/nvidia.Kbuild etc, foreach-included in kernel/Kbuild) —
        # without it that foreach is empty and the conftest.sh
        # feature-detection header (nvidia/conftest/headers.h) never gets
        # wired in as a build prerequisite at all, so nv.c's
        # #include "conftest.h" fails outright. Confirmed by direct
        # iteration against a real build.
        #
        # See the ccflags-y sed patch above for the EXTRA_CFLAGS fix — this
        # single driver source tree still isn't guaranteed to build clean
        # against every kernel HippOS ships (470.256.02 predates some 2025+
        # kernel API churn, e.g. timespec_to_ns/efi_enabled signature
        # changes) — that's real upstream driver/kernel version drift, not
        # a build-plumbing bug, and the per-release WARNING below already
        # degrades that tier to nouveau gracefully rather than failing the
        # whole build.
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

    rm -rf "${EXTRACT_DIR}"
done

[[ "${BUILT_ANY}" -eq 1 ]] || log "WARNING: no legacy NVIDIA tier produced a working kernel module — older GPUs will fall back to nouveau"

log "Done. Artifact at ${STAGING}"
