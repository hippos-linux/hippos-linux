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

PATCH_DIR="${REPO_ROOT}/packages/emulators/${NAME}"
for patch in 001-renameat2-einval-fallback.patch; do
    if git -C "${SRC}" apply --reverse --check "${PATCH_DIR}/${patch}" >/dev/null 2>&1; then
        log "Patch already applied: ${patch}"
    else
        git -C "${SRC}" apply "${PATCH_DIR}/${patch}"
    fi
done

BUILD_PACKAGES=(libbsd-dev libunwind-dev libglfw3-dev)
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
make -C "${SRC}" x86_64 -j"$(nproc)" "${MAKE_VARS[@]}"

rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin"
cp -a "${SRC}/lunaria" "${SRC}/runtime" "${SRC}/syslib-arm64" "${SRC}/keymaps" "${SRC}/scripts" "${SRC}/lunaria.conf.sample" "${STAGING}/bin/"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
