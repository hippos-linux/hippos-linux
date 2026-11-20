#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='u-boot-rk3326'
UBOOT_REF='2492a3e467e332e2350d987234ce6123700b3392'
UBOOT_URL="https://github.com/ROCKNIX/hardkernel-uboot/archive/${UBOOT_REF}.tar.gz"
UBOOT_SHA256='d8b358f20394ff1c901af989d0a5b7740f46708bd93ff714459d7bc3794a72f8'
RKBIN_REF='3e288fe814e059dd06833495f845cab04ac20a5c'
declare -A RKBIN_FILES=(
    [bin/rk33/rk3326_ddr_333MHz_v2.12.bin]='285a87e760a3586953f637b6de0fe80745b0ecf455dfb052bc3ecfc8b756cb7e'
    [bin/rk33/rk3326_miniloader_v1.40.bin]='473aacd5378f356757a71efeb54f4339925db154fbce288df7e3c1177f45bc28'
    [bin/rk33/rk3326_bl31_v1.37.elf]='1174a89ad30b7e4fb21d3f3794f23946f659c45de8e0414c9dbf717199f43b7b'
    [tools/loaderimage]='e26a311d449c6254d0d89ecaf8cd1870438205e07a66b27265d68830b8977439'
    [tools/trust_merger]='8356dd5f0258a2ef3bf854efaea7b86047d73e7844169a1c81ff354fb94955bd'
)

PKG_DIR="/work/packages/bootloader/${NAME}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/bootloader}"
BUILD="${WORK_ROOT}/${NAME}"
SRC="${BUILD}/u-boot"
RKBIN="${BUILD}/rkbin"
STAGING="${ARTIFACT_ROOT}/${BUILD_TARGET}/bootloader"
UBOOT_MAKE=(make ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- KCFLAGS=-Wno-error=unused-but-set-variable)

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
chmod +x "${RKBIN}/tools/"*

log "Building U-Boot ${UBOOT_REF:0:12}"
rm -rf "${SRC}"
mkdir -p "${SRC}"
tar -C "${SRC}" --strip-components=1 -xzf "${BUILD}/u-boot.tar.gz"
patch -d "${SRC}" -p1 --silent < "${PKG_DIR}/fix-building.patch"
cp "${PKG_DIR}/rk3326_defconfig" "${SRC}/configs/hippos_rk3326_defconfig"
"${UBOOT_MAKE[@]}" -C "${SRC}" hippos_rk3326_defconfig
"${UBOOT_MAKE[@]}" -C "${SRC}" -j"$(nproc)" CONFIG_MKIMAGE_DTC_PATH=scripts/dtc/dtc

log "Packing uboot.bin"
cd "${SRC}"
tools/mkimage -n px30 -T rksd -d "${RKBIN}/bin/rk33/rk3326_ddr_333MHz_v2.12.bin" -C bzip2 idbloader.img
cat "${RKBIN}/bin/rk33/rk3326_miniloader_v1.40.bin" >> idbloader.img
"${RKBIN}/tools/loaderimage" --pack --uboot u-boot-dtb.bin uboot.img 0x00200000
cat > trust.ini <<EOF
[BL30_OPTION]
SEC=0
[BL31_OPTION]
SEC=1
PATH=${RKBIN}/bin/rk33/rk3326_bl31_v1.37.elf
ADDR=0x00010000
[BL32_OPTION]
SEC=0
[BL33_OPTION]
SEC=0
[OUTPUT]
PATH=trust.img
EOF
"${RKBIN}/tools/trust_merger" trust.ini
rm -f uboot.bin
dd if=idbloader.img of=uboot.bin bs=512 seek=0 conv=notrunc status=none
dd if=uboot.img of=uboot.bin bs=512 seek=16320 conv=notrunc status=none
dd if=trust.img of=uboot.bin bs=512 seek=24512 conv=notrunc status=none

rm -rf "${STAGING}"
mkdir -p "${STAGING}"
install -m644 uboot.bin "${STAGING}/uboot.bin"
tools/mkimage -A arm64 -T script -C none -n "HippOS boot" -d "${PKG_DIR}/boot.cmd" "${STAGING}/boot.scr"
printf '%s\n' "${UBOOT_REF}" > "${STAGING}/version"

log "Done. Artifact at ${STAGING}"
