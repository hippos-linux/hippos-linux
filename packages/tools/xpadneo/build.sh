#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='xpadneo'
REPO='https://github.com/atar-axis/xpadneo.git'
# Pinned, not github_latest_tag like the other tools — the built .ko's vermagic
# must match the target kernel exactly, so floating to whatever's newest on
# every build buys nothing here and just adds an untested variable. Bump
# deliberately.
TAG="${XPADNEO_TAG:-v0.10.4}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

# Covers Xbox One/Series-protocol BT pads only — xpad (in-tree) already
# handles Xbox 360 and USB mode. Built against the standard kernel variant
# only: configure-rootfs.sh doesn't install lts headers into the rootfs
# either, and this needs a real headers artifact from build/build-kernel.sh.
ARCH="${ARCH:-amd64}"
KERNEL_ARTIFACTS_DIR="${ARTIFACT_ROOT}/${ARCH}/kernel/standard"
HEADERS_DEB="$(ls "${KERNEL_ARTIFACTS_DIR}"/linux-headers-*.deb 2>/dev/null | head -1)"
[[ -n "${HEADERS_DEB}" ]] || { log "No kernel headers artifact at ${KERNEL_ARTIFACTS_DIR} — run build/build-kernel.sh first"; exit 1; }

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${TAG}"
    git clone --depth=1 --branch "${TAG}" "${REPO}" "${SRC}"
fi

log "Extracting kernel headers from $(basename "${HEADERS_DEB}")"
HEADERS_ROOT="${WORK_ROOT}/${NAME}/headers"
rm -rf "${HEADERS_ROOT}"
mkdir -p "${HEADERS_ROOT}"
dpkg-deb -x "${HEADERS_DEB}" "${HEADERS_ROOT}"
KERNEL_SOURCE_DIR="$(find "${HEADERS_ROOT}/usr/src" -maxdepth 1 -type d -name 'linux-headers-*' | head -1)"
[[ -n "${KERNEL_SOURCE_DIR}" ]] || { log "Couldn't find extracted headers under ${HEADERS_ROOT}/usr/src"; exit 1; }
KVER="$(basename "${KERNEL_SOURCE_DIR}")"
KVER="${KVER#linux-headers-}"

log "Building hid-xpadneo against kernel ${KVER}"
make -C "${SRC}/hid-xpadneo" KERNEL_SOURCE_DIR="${KERNEL_SOURCE_DIR}" modules

log "Staging"
mkdir -p "${STAGING}/lib/modules/${KVER}/extra" \
    "${STAGING}/etc/modprobe.d" \
    "${STAGING}/etc/udev/rules.d"
cp "${SRC}/hid-xpadneo/src/hid-xpadneo.ko" "${STAGING}/lib/modules/${KVER}/extra/"
cp "${SRC}/hid-xpadneo/etc-modprobe.d/"*.conf "${STAGING}/etc/modprobe.d/"
cp "${SRC}/hid-xpadneo/etc-udev-rules.d/"*.rules "${STAGING}/etc/udev/rules.d/"

log "Done. Artifact at ${STAGING}"
