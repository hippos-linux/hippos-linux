#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='xonedo'
REPO='https://github.com/OpenGamingCollective/xonedo.git'
# Pinned like xpadneo — the built .ko's vermagic must match the target kernel
# exactly, so floating to latest buys nothing and adds an untested variable.
TAG="${XONEDO_TAG:-v0.5.7-ogc1}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

# Xbox Wireless Dongle only — doesn't overlap xpadneo (Bluetooth) or the
# in-tree xpad (wired/360). Built against both kernel variants — lts
# exists for hardware regressing on the stable series, and that
# population losing controller support too defeats the point of it (see
# configure-rootfs.sh, which now installs lts headers into the rootfs for
# the same reason). Staged output is keyed by kernel release string, so
# both coexist under the same STAGING tree without conflict.
ARCH="${ARCH:-amd64}"

log "Installing bsdtar (needed to unpack Microsoft's dongle firmware .cab files)"
apt-get update -qq
apt-get install -y --no-install-recommends libarchive-tools

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${TAG}"
    git clone --depth=1 --branch "${TAG}" "${REPO}" "${SRC}"
fi

mkdir -p "${STAGING}/lib/firmware" "${STAGING}/etc/modprobe.d"

BUILT_ANY=0
for variant in standard lts; do
    KERNEL_ARTIFACTS_DIR="${ARTIFACT_ROOT}/${ARCH}/kernel/${variant}"
    HEADERS_DEB="$(ls "${KERNEL_ARTIFACTS_DIR}"/linux-headers-*.deb 2>/dev/null | head -1)"
    if [[ -z "${HEADERS_DEB}" ]]; then
        if [[ "${variant}" == "standard" ]]; then
            log "No kernel headers artifact at ${KERNEL_ARTIFACTS_DIR} — run build/build-kernel.sh first"
            exit 1
        fi
        log "No lts headers artifact — skipping lts (run build/build-kernels.sh for both)"
        continue
    fi

    log "Extracting kernel headers from $(basename "${HEADERS_DEB}") (${variant})"
    HEADERS_ROOT="${WORK_ROOT}/${NAME}/headers-${variant}"
    rm -rf "${HEADERS_ROOT}"
    mkdir -p "${HEADERS_ROOT}"
    dpkg-deb -x "${HEADERS_DEB}" "${HEADERS_ROOT}"
    KERNEL_SOURCE_DIR="$(find "${HEADERS_ROOT}/usr/src" -maxdepth 1 -type d -name 'linux-headers-*' | head -1)"
    [[ -n "${KERNEL_SOURCE_DIR}" ]] || { log "Couldn't find extracted headers under ${HEADERS_ROOT}/usr/src"; exit 1; }
    KVER="$(basename "${KERNEL_SOURCE_DIR}")"
    KVER="${KVER#linux-headers-}"

    log "Building xone_* modules against kernel ${KVER} (${variant})"
    make -C "${KERNEL_SOURCE_DIR}" M="${SRC}" clean
    make -C "${KERNEL_SOURCE_DIR}" M="${SRC}" modules

    mkdir -p "${STAGING}/lib/modules/${KVER}/extra"
    cp "${SRC}"/xone_*.ko "${STAGING}/lib/modules/${KVER}/extra/"
    BUILT_ANY=1
done

[[ "${BUILT_ANY}" -eq 1 ]] || { log "Built for no kernel variant"; exit 1; }

log "Fetching dongle firmware from Microsoft's Windows Update CDN (via upstream's own verified script)"
mkdir -p /lib/firmware
bash "${SRC}/install/firmware.sh" --skip-disclaimer

log "Staging shared files"
cp /lib/firmware/xone_dongle_*.bin "${STAGING}/lib/firmware/"
cp "${SRC}/install/modprobe.conf" "${STAGING}/etc/modprobe.d/xone-blacklist.conf"

log "Done. Artifact at ${STAGING}"
