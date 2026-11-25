#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='lunaria'
REPO='https://github.com/yui0/lunaria'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

BUILD_PACKAGES=(libbsd-dev libunwind-dev libglfw3-dev libwayland-dev libegl-dev libgles-dev libasound2-dev libssl-dev zlib1g-dev)
missing=()
for package in "${BUILD_PACKAGES[@]}"; do
    dpkg -s "${package}${DEB_TARGET_SUFFIX}" >/dev/null 2>&1 || missing+=("${package}${DEB_TARGET_SUFFIX}")
done
if (( ${#missing[@]} )); then
    apt-get update -qq && apt-get install -y --no-install-recommends "${missing[@]}"
fi

MAKE_VARS=(BUILD_DIR="${BUILD}" DYNARMIC_CMAKE_FLAGS=-DDYNARMIC_USE_BUNDLED_EXTERNALS=ON)
rm -rf "${BUILD}" "${SRC}/dynarmic/build"
mkdir -p "${BUILD}"
log "Building Lunaria ${TAG}"
make -C "${SRC}" dynarmic-build -j"$(nproc)" "${MAKE_VARS[@]}"
make -C "${SRC}" syslib-arm64/libm.so syslib-arm64/libc-pure.so "${MAKE_VARS[@]}"
case "${ARCH}" in
    amd64) HOST_TARGET=(x86_64) ;;
    arm64) HOST_TARGET=(all OPENH264_ARCH=linux-arm64) ;;
esac
make -C "${SRC}" "${HOST_TARGET[@]}" -j"$(nproc)" "${MAKE_VARS[@]}"

rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin"
cp -a "${SRC}/lunaria" "${SRC}/runtime" "${SRC}/syslib-arm64" "${SRC}/keymaps" "${SRC}/scripts" "${SRC}/lunaria.conf.sample" "${STAGING}/bin/"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
