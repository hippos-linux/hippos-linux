#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='nvidia-legacy'

REPO_ROOT="${REPO_ROOT:-/work}"
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
    "580:580.173.02:8d8eb9001e05a9a8a663d3d5d304feb64ef2844ee185ccdfd952786820f46e1b"
    "470:470.256.02:d6451862deb695bb0447f3b7cd6268f73e81168c10e2c10597ff3fa01349b1de"
    "390:390.157:5bebbca6e8fed5d6b9d81070fb9e351f18edc534952553cbdc71e8fd0b9b328a"
    "340:340.108:c671d4f1b7c09bc1af079b98b447adb06d704b04f802f7045a611fa50133b71b"
)

# Community-maintained kernel-compat patches, vendored under
# build/patches/nvidia-legacy/<tier>/ — same role as the D0023R CRT kernel
# patches (build/patches/kernel/${ARCH}/crt/), a different problem shape:
# these are cumulative per-kernel-version fixes meant to all be applied in a
# fixed order (not mutually exclusive per series), so every tier applies its
# whole list unconditionally rather than picking a nearest-series match.
# 470's list matches joanbm/nvidia-470xx-linux-mainline's own apply order
# (reaches kernel 7.2); 390's matches the AUR nvidia-390xx-utils PKGBUILD's
# prepare() order (reaches 7.0); 340's is archlinux-jerry/nvidia-340xx's
# numbered series (only reaches 6.15 — the current AUR nvidia-340xx-utils
# package ships no compat patches at all, 340.108 is the least maintained of
# the three branches). 580 is pinned to 580.173.02, not the first 580.x
# release — 580.126.09 fails to build against HippOS's kernel (7.1.8):
# kernel/common/inc/nv-linux.h unconditionally includes <linux/of_gpio.h>,
# which upstream dropped entirely, and nv-mmap.c's hand-rolled VMA locking
# fallback (VMA_LOCK_OFFSET, __is_vma_write_locked) targets an older kernel
# VMA-lock internal representation than 7.1.8 actually has — both confirmed
# by attempting the build against HippOS's real kernel-headers package, not
# assumed from changelog reading. Patching driver-side reimplementations of
# kernel-internal locking is exactly the kind of fix to get from upstream
# rather than hand-roll: got worse (not better) with more digging, since a
# subtly-wrong VMA lock patch fails silently under load, not at compile
# time. 580.173.02 has NVIDIA's own proper fix for both (conftest-guarded
# <linux/of_gpio.h> with a real of_get_named_gpio() compat shim, and a
# VM_REFCNT_EXCLUDE_READERS_FLAG-aware nv_is_vma_write_locked()) — verified
# against HippOS's actual kernel headers, not just release-note reading.
# 580's patch list was just the one generic LDFLAGS fix every tier here
# could arguably use (upstream nvidia.ko/nvidia-modeset.ko Kbuild links
# with bare $(LD) instead of $(LD) $(LDFLAGS), which only bites cross-arch
# toolchains — harmless either way, kept for parity) until kernel 7.2's
# strncpy removal broke both 580 and 390 against HippOS's `standard`
# kernel (confirmed via a real 0.6.2 release build) — no upstream community
# patch set exists yet for 580 (too new to be "legacy" in the community's
# sense), and 390's own set stops at kernel 7.0. Both got a hand-ported
# fix (kernel-7.2-strncpy-removal.patch in each tier's directory),
# adapted line-for-line from 470's own already-vendored fix for the exact
# same kernel commit against the same four files — see that patch's own
# header comment. 390 also appeared to need a second, much bigger fix (the
# DRM subsystem's own struct drm_atomic_state -> drm_atomic_commit
# rename) — a hand-ported version of that was tried and built clean in
# isolated testing, but reproducibly failed to apply inside the actual
# builder container on two separate full release builds, and — the
# important part — 390 built successfully on both kernels in both of
# those same runs regardless of that patch never applying. Evidence says
# it isn't actually needed against HippOS's real target kernels; removed
# rather than shipped as a patch that reliably logs a scary warning and
# does nothing. Patch paths are
# "a/kernel/..." for 390/340/580 (apply from the extracted driver's top
# dir) but bare "a/conftest.sh" etc for 470 (apply from its
# kernel/ subdir) — an artifact of how each upstream generated its diffs,
# not something to normalize away.
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
                disable-objtool-override.patch \
                enable-drm-modeset-by-default.patch
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
                kernel-7.2-strncpy-removal.patch
            ;;
        340)
            # Numbered 0001-0019, filename sort is the correct apply order.
            (cd "${REPO_ROOT}/build/patches/nvidia-legacy/340" 2>/dev/null && ls -1 *.patch 2>/dev/null | sort)
            ;;
    esac
}

# 470's patches were generated with the extracted driver's kernel/
# subdirectory as the diff root; 390's and 340's were generated one level up
# (their hunk paths already read "a/kernel/...").
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

    # Every driver source tree accumulates its -I/-D flags into EXTRA_CFLAGS
    # and (in the two newer, Kbuild-based tiers) carries a comment claiming
    # "newer kernels append $(EXTRA_CFLAGS) to ccflags-y for compatibility"
    # — that compat shim no longer exists anywhere in current mainline
    # kbuild, so EXTRA_CFLAGS silently never reaches the real per-object
    # compile. Confirmed by direct iteration: this alone was the root cause
    # of three separate-looking failures on tier 470 — nvmisc.h not found
    # (needs -I$(src)/common/inc), stdarg.h not found (nv_stdarg.h's
    # correct <linux/stdarg.h> path is gated behind
    # -DNV_KERNEL_INTERFACE_LAYER), and bogus uint32_t/stdint.h errors
    # (nv-ioctl-numa.h's correct <linux/types.h> path is gated behind the
    # same macro). Forwarding EXTRA_CFLAGS into ccflags-y (kbuild's actual
    # always-applied mechanism) fixes all three at once, and is the fix
    # NVIDIA's own comment already describes as the intended behavior — the
    # 6.15+ compat patches above independently make the same fix by renaming
    # EXTRA_CFLAGS to ccflags-y outright, which makes this sed a no-op on
    # patched kernel versions and a fallback on unpatched ones.
    #
    # 340.108 predates the Kbuild-based layout entirely (flat kernel/
    # Makefile + nvidia-modules-common.mk, no per-module Kbuild fragments,
    # no NV_KERNEL_INTERFACE_LAYER macro) and its Makefile has no
    # ccflags-y-awareness comment at all — this bug hits it just as hard,
    # just with no upstream fix to lean on, since none of its vendored
    # patches touch this. Same forwarding fix, applied to whichever file
    # actually accumulates EXTRA_CFLAGS for that tier's layout.
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

    # Xorg driver + GLX extension module — tier-prefixed filenames so they
    # never collide with nvidia-open's or each other's. No underscore before
    # "legacy": Xorg strips internal underscores from a Driver name before
    # searching for its module file, so hippos-gpu-init's OutputClass rewrite
    # (nvidia_switch_tier) ends up asking for "nvidia${tier}legacy_drv.so" —
    # stage it under that exact name or Xorg's LoadModule reports "module
    # does not exist" and silently falls back to nvidia-open's driver
    # (real hardware, tier 580: GTX 970 forced onto swrast the whole session).
    [[ -f "${EXTRACT_DIR}/nvidia_drv.so" ]] && \
        cp "${EXTRACT_DIR}/nvidia_drv.so" "${STAGING}/usr/lib/xorg/modules/drivers/nvidia${tier}legacy_drv.so"
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
