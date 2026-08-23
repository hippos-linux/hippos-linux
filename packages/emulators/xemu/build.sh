#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='xemu'
REPO='https://github.com/xemu-project/xemu.git'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

for patch in 001-fix-optionrom-makefile.patch 002-eeprom-path.patch 003-hide-menu.patch; do
    [[ -f "${PATCH_DIR}/${patch}" ]] || {
        if [[ "${patch}" == '003-hide-menu.patch' ]]; then
            log "Optional patch ${patch} missing; skipping"
            continue
        fi
        die "Required patch missing: ${PATCH_DIR}/${patch}"
    }

    if git -C "${SRC}" apply --reverse --check "${PATCH_DIR}/${patch}" >/dev/null 2>&1; then
        log "Patch already applied: ${patch}"
        continue
    fi

    if ! git -C "${SRC}" apply --3way "${PATCH_DIR}/${patch}"; then
        if [[ "${patch}" == '003-hide-menu.patch' ]]; then
            log "Skipping stale optional patch ${patch}"
            continue
        fi
        die "Failed to apply required patch ${patch}"
    fi
done

mkdir -p "${STAGING}/bin" "${STAGING}/data"

if [[ "${ARCH:-amd64}" == "arm64" ]] && [[ "$(uname -m)" == "x86_64" ]]; then
    # glslang subproject hardcodes x86-only compiler flags (-mcx16, -msse2, -msse4.1)
    # in its meson.build using build_machine detection. Patch them out before build.
    find "${SRC}" \( -path '*/glslang*' -o -path '*/subprojects/glslang*' \) \
        -name 'meson.build' \
        -exec sed -i "s/-mcx16//g; s/-msse2//g; s/-msse4\.1//g; s/-mfpmath=sse//g" {} \; \
        2>/dev/null || true
fi

log "Building with upstream build.sh"
cd "${SRC}"
./build.sh

if [[ ! -x "${SRC}/dist/xemu" ]]; then
    die "xemu dist binary was not produced"
fi

log "Staging binary"
cp "${SRC}/dist/xemu" "${STAGING}/bin/xemu"
chmod +x "${STAGING}/bin/xemu"
# Stripping is now handled centrally by build/strip-emulator-payload.sh (called from both configure-rootfs.sh and build-emulators.sh).

mkdir -p "${STAGING}/lib"
cp /usr/lib/${GNU_ARCH}/libtomlplusplus.so.3* "${STAGING}/lib/" 2>/dev/null || true
patchelf --set-rpath '$ORIGIN/../lib' "${STAGING}/bin/xemu" 2>/dev/null || true

if [[ -d "${SRC}/data" ]]; then
    cp -a "${SRC}/data/." "${STAGING}/data/"
fi

if [[ ! -f "${STAGING}/data/xbox_hdd.qcow2" ]]; then
    HDD_ZIP="${WORK_ROOT}/${NAME}/xbox_hdd.qcow2.zip"
    if [[ ! -f "${HDD_ZIP}" ]]; then
        log "Downloading xemu HDD image"
        curl -fL -o "${HDD_ZIP}" \
            'https://github.com/mborgerson/xemu-hdd-image/releases/download/1.0/xbox_hdd.qcow2.zip'
    fi
    unzip -o "${HDD_ZIP}" xbox_hdd.qcow2 -d "${STAGING}/data" >/dev/null
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
