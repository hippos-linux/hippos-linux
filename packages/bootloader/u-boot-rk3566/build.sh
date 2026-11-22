#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='u-boot-rk3566'
UBOOT_REF='v2026.01'
UBOOT_URL="https://github.com/u-boot/u-boot/archive/${UBOOT_REF}.tar.gz"
UBOOT_SHA256='03bb43c58d2343ee48dd191e0f181f0108425b179d84519add3a977071c3f654'
UBOOT_DEFCONFIG='anbernic-rgxx3-rk3566_defconfig'
RKBIN_REF='3e288fe814e059dd06833495f845cab04ac20a5c'
BL31='bin/rk35/rk3568_bl31_v1.46.elf'
DDR='bin/rk35/rk3568_ddr_1056MHz_v1.26.bin'
declare -A RKBIN_FILES=(
    [${BL31}]='c81ac7e8e1fd727cf7f0db62a9aaea760bde2b270e34d98eb264a264b86df749'
    [${DDR}]='1af305b6930af4d7afe3af8ddc88d1b353427dae451bfdb4a2e1dbc52488f725'
)

PKG_DIR="/work/packages/bootloader/${NAME}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/bootloader}"
BUILD="${WORK_ROOT}/${NAME}"
SRC="${BUILD}/u-boot"
RKBIN="${BUILD}/rkbin"
STAGING="${ARTIFACT_ROOT}/${BUILD_TARGET}/bootloader"
UBOOT_MAKE=(make ARCH=arm CROSS_COMPILE=aarch64-linux-gnu-)

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

fetch_verified() {
    local url="$1" dest="$2" sha256="$3"
    [[ -f "${dest}" ]] && echo "${sha256}  ${dest}" | sha256sum --check --quiet 2>/dev/null && return 0
    mkdir -p "$(dirname "${dest}")"
    curl -fsSL -o "${dest}" "${url}"
    echo "${sha256}  ${dest}" | sha256sum --check --quiet
}

fetch_verified "${UBOOT_URL}" "${BUILD}/u-boot.tar.gz" "${UBOOT_SHA256}"
for file in "${!RKBIN_FILES[@]}"; do
    fetch_verified "https://raw.githubusercontent.com/rockchip-linux/rkbin/${RKBIN_REF}/${file}" \
        "${RKBIN}/${file}" "${RKBIN_FILES[${file}]}"
done

log "Building U-Boot ${UBOOT_REF}"
rm -rf "${SRC}"
mkdir -p "${SRC}"
tar -C "${SRC}" --strip-components=1 -xzf "${BUILD}/u-boot.tar.gz"
cat "${SRC}/configs/${UBOOT_DEFCONFIG}" "${PKG_DIR}/rk3566.config" > "${SRC}/configs/hippos_rk3566_defconfig"
"${UBOOT_MAKE[@]}" -C "${SRC}" hippos_rk3566_defconfig
"${UBOOT_MAKE[@]}" -C "${SRC}" -j"$(nproc)" \
    BL31="${RKBIN}/${BL31}" ROCKCHIP_TPL="${RKBIN}/${DDR}"

rm -rf "${STAGING}"
mkdir -p "${STAGING}"
install -m644 "${SRC}/u-boot-rockchip.bin" "${STAGING}/uboot.bin"
"${SRC}/tools/mkimage" -A arm64 -T script -C none -n "HippOS boot" -d "${PKG_DIR}/boot.cmd" "${STAGING}/boot.scr"
printf '%s\n' "${UBOOT_REF}" > "${STAGING}/version"

log "Done. Artifact at ${STAGING}"
