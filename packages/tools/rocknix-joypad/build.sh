#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='rocknix-joypad'
REPO='https://github.com/ROCKNIX/rocknix-joypad.git'
REF="${ROCKNIX_JOYPAD_REF:-ac1be0fa0c4e1f7feb9a900fc428d7ac6014029c}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/${BUILD_TARGET}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -d "${SRC}/.git" || "$(git -C "${SRC}" rev-parse HEAD)" != "${REF}" ]]; then
    rm -rf "${SRC}"
    git clone --quiet "${REPO}" "${SRC}"
    git -C "${SRC}" checkout --quiet "${REF}"
fi

BUILT_ANY=0
for variant in $(kernel_variants); do
    KERNEL_SOURCE_DIR="$(extract_kernel_headers "${variant}" "${WORK_ROOT}/${NAME}/headers-${variant}")" || {
        log "No ${variant} kernel headers artifact — skipping ${variant}"
        continue
    }
    KVER="$(basename "${KERNEL_SOURCE_DIR}")"
    KVER="${KVER#linux-headers-}"
    log "Building joypad drivers against kernel ${KVER} (${variant})"
    prepare_kernel_headers "${KERNEL_SOURCE_DIR}"
    kernel_module_make -C "${KERNEL_SOURCE_DIR}" M="${SRC}" clean >/dev/null 2>&1 || true
    kernel_module_make -C "${KERNEL_SOURCE_DIR}" M="${SRC}" DEVICE=RK3326 modules

    mkdir -p "${STAGING}/lib/modules/${KVER}/extra"
    cp "${SRC}/rocknix-joypad.ko" "${SRC}/rocknix-singleadc-joypad.ko" "${STAGING}/lib/modules/${KVER}/extra/"
    BUILT_ANY=1
done

[[ "${BUILT_ANY}" -eq 1 ]] || { log "Built for no kernel variant"; exit 1; }

log "Done. Artifact at ${STAGING}"
