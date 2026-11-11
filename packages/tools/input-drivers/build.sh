#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='input-drivers'
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
STAGING="${ARTIFACT_ROOT}/${ARCH}/tools/${NAME}"

NEW_LG4FF_REF="${NEW_LG4FF_REF:-2092db19f7b40854e0427a1b2e39eda9f8d0c3cd}"
HID_TMFF2_REF="${HID_TMFF2_REF:-d890a93105a0aa52028ac49282fa1b579e12566e}"
HID_T150_REF="${HID_T150_REF:-f7ecb30c65ee5f7870e921bc0a2354df8e1e8100}"
TRUEFORCE_REF="${TRUEFORCE_REF:-v0.42.4}"
GUNCON3_REF="${GUNCON3_REF:-0dfe0feaa2afc37a8a70f6cd0f6c803ee4d89f40}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

fetch() {
    local repo="$1" ref="$2" dest="$3"
    [[ -d "${dest}/.git" && "$(git -C "${dest}" rev-parse HEAD)" == "$(git -C "${dest}" rev-parse "${ref}^{commit}" 2>/dev/null)" ]] && return 0
    rm -rf "${dest}"
    git clone --quiet --recurse-submodules "${repo}" "${dest}"
    git -C "${dest}" checkout --quiet "${ref}"
    git -C "${dest}" submodule update --quiet --init --recursive
}

SRC="${WORK_ROOT}/${NAME}"
fetch https://github.com/berarma/new-lg4ff.git "${NEW_LG4FF_REF}" "${SRC}/new-lg4ff"
fetch https://github.com/Kimplul/hid-tmff2.git "${HID_TMFF2_REF}" "${SRC}/hid-tmff2"
fetch https://github.com/scarburato/t150_driver.git "${HID_T150_REF}" "${SRC}/t150"
fetch https://github.com/mescon/logitech-trueforce-linux-driver.git "${TRUEFORCE_REF}" "${SRC}/trueforce"
fetch https://github.com/pcnimdock/guncon3_dkms.git "${GUNCON3_REF}" "${SRC}/guncon3"

build_module() {
    local dir="$1" ksrc="$2"
    shift 2
    kernel_module_make -C "${ksrc}" M="${dir}" clean >/dev/null 2>&1 || true
    kernel_module_make -C "${ksrc}" M="${dir}" "$@" modules
}

BUILT_ANY=0
for variant in $(kernel_variants); do
    KERNEL_SOURCE_DIR="$(extract_kernel_headers "${variant}" "${SRC}/headers-${variant}")" || {
        log "No ${variant} kernel headers artifact — skipping ${variant}"
        continue
    }
    KVER="$(basename "${KERNEL_SOURCE_DIR}")"
    KVER="${KVER#linux-headers-}"
    log "Building input drivers against kernel ${KVER} (${variant})"
    prepare_kernel_headers "${KERNEL_SOURCE_DIR}"

    build_module "${SRC}/new-lg4ff" "${KERNEL_SOURCE_DIR}"
    build_module "${SRC}/hid-tmff2" "${KERNEL_SOURCE_DIR}"
    build_module "${SRC}/t150/hid-t150" "${KERNEL_SOURCE_DIR}"
    build_module "${SRC}/trueforce/mainline" "${KERNEL_SOURCE_DIR}"
    build_module "${SRC}/guncon3/src" "${KERNEL_SOURCE_DIR}" KCFLAGS=-Wno-error=unused-variable

    mkdir -p "${STAGING}/lib/modules/${KVER}/updates" "${STAGING}/lib/modules/${KVER}/extra"
    cp "${SRC}/new-lg4ff/hid-logitech-new.ko" "${STAGING}/lib/modules/${KVER}/updates/hid-logitech.ko"
    cp "${SRC}/hid-tmff2/hid-tmff-new.ko" "${SRC}/t150/hid-t150/hid-t150.ko" \
       "${SRC}/trueforce/mainline/hid-logitech-dd.ko" "${SRC}/guncon3/src/guncon3.ko" \
       "${STAGING}/lib/modules/${KVER}/extra/"
    find "${SRC}/hid-tmff2" -name 'hid-tminit.ko' -exec cp {} "${STAGING}/lib/modules/${KVER}/extra/" \;
    BUILT_ANY=1
done

[[ "${BUILT_ANY}" -eq 1 ]] || { log "Built for no kernel variant"; exit 1; }

log "Staging udev rules"
mkdir -p "${STAGING}/etc/udev/rules.d"
cp "${SRC}/trueforce/udev/70-logitech-trueforce.rules" "${SRC}/trueforce/udev/72-logitech-g923-rebind.rules" \
   "${STAGING}/etc/udev/rules.d/"
find "${SRC}/hid-tmff2" "${SRC}/t150" -name '71-thrustmaster-steamdeck.rules' -exec cp {} "${STAGING}/etc/udev/rules.d/" \;

log "Done. Artifact at ${STAGING}"
