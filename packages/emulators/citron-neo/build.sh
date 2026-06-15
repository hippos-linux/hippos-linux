#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='citron-neo'
REPO='https://github.com/citron-neo/emulator'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build-release"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

git -C "${SRC}" submodule update --init --recursive

source "/work/build/qt611-env.sh"

# GCC 14 false positive: addr is set by ParseGhidraCsvLine (out-param) before use,
# but the compiler can't see through it. Initialize to suppress -Werror=maybe-uninitialized.
sed -i 's/^\( *\)u64 addr;$/\1u64 addr = 0;/' \
    "${SRC}/src/citron/debugger/function_browser.cpp"

rm -rf "${STAGING}"
rm -rf "${BUILD}"
mkdir -p "${STAGING}/bin"

_citron_arch_flags=()
[[ "${ARCH:-amd64}" == "amd64" ]] && _citron_arch_flags=(
    -DCMAKE_C_FLAGS="-mtls-dialect=gnu2"
    -DCMAKE_CXX_FLAGS="-mtls-dialect=gnu2"
)

log "Configuring Citron Neo ${TAG}"
cmake -S "${SRC}" -B "${BUILD}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}" \
    -DCITRON_USE_CPM=ON \
    -DCITRON_USE_BUNDLED_VCPKG=OFF \
    -DCITRON_USE_BUNDLED_QT=OFF \
    -DUSE_SYSTEM_QT=ON \
    -DENABLE_QT6=ON \
    -DCITRON_USE_BUNDLED_FFMPEG=OFF \
    -DBUILD_TESTING=OFF \
    -DCITRON_TESTS=OFF \
    -DCITRON_DOWNLOAD_TIME_ZONE_DATA=ON \
    -DCITRON_CHECK_SUBMODULES=OFF \
    -DCITRON_USE_LLVM_DEMANGLE=OFF \
    -DCITRON_USE_QT_MULTIMEDIA=ON \
    -DCITRON_USE_QT_WEB_ENGINE=OFF \
    -DENABLE_QT_TRANSLATION=ON \
    -DUSE_DISCORD_PRESENCE=ON \
    -DENABLE_WEB_SERVICE=ON \
    -DENABLE_OPENSSL=ON \
    -DBUNDLE_SPEEX=ON \
    -DCITRON_USE_FASTER_LD=OFF \
    -DCITRON_USE_EXTERNAL_Vulkan_HEADERS=ON \
    -DCITRON_USE_EXTERNAL_VULKAN_UTILITY_LIBRARIES=ON \
    -DCITRON_USE_AUTO_UPDATER=OFF \
    -DCITRON_BUILD_TYPE=Release \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="/opt/hippos/qt/6.11/lib" \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    "${_citron_arch_flags[@]}" \
    -Wno-dev

log "Building Citron Neo"
cmake --build "${BUILD}" -j"$(nproc)"

if [[ -d "${BUILD}/bin" ]]; then
    cp -a "${BUILD}/bin/." "${STAGING}/bin/"
fi

if [[ -x "${STAGING}/bin/citron" && ! -e "${STAGING}/bin/citron-neo" ]]; then
    ln -s citron "${STAGING}/bin/citron-neo"
fi

[[ -x "${STAGING}/bin/citron" || -x "${STAGING}/bin/citron-neo" ]] \
    || die "Citron Neo executable was not produced"

find "${STAGING}/bin" -maxdepth 1 -type f -perm /111 -exec strip {} \; 2>/dev/null || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
