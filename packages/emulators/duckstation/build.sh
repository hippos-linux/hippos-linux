#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='duckstation'
REPO='https://github.com/stenzek/duckstation.git'
DEPS_REPO='https://github.com/duckstation/dependencies/releases/latest/download/deps-linux-x64.tar.xz'
REF="${DUCKSTATION_REF:-master}"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build-release"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${REF}" "${SRC}"

git -C "${SRC}" submodule update --init --recursive

source "/work/build/qt611-env.sh"

mkdir -p "${SRC}/dep/prebuilt" "${STAGING}/bin"

if [[ ! -f "${SRC}/dep/prebuilt/.deps-linux-x64.done" ]]; then
    log "Downloading DuckStation deps-linux-x64"
    curl -fL "${DEPS_REPO}" -o "${WORK_ROOT}/${NAME}/deps-linux-x64.tar.xz"

    log "Extracting DuckStation prebuilt dependencies"
    tar -xJf "${WORK_ROOT}/${NAME}/deps-linux-x64.tar.xz" -C "${SRC}/dep/prebuilt"
    touch "${SRC}/dep/prebuilt/.deps-linux-x64.done"
fi

rm -rf "${BUILD}"

# Remove FindSoundTouch.cmake so cmake uses the prebuilt's SoundTouchConfig.cmake
# (which defines SoundTouch::SoundTouchDLL) instead of the module (which defines
# SoundTouch::SoundTouch only)
rm -f "${SRC}/CMakeModules/FindSoundTouch.cmake"

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_EXE_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_MODULE_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_SHARED_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON \
    -DCMAKE_PREFIX_PATH="${QT_ROOT};${SRC}/dep/prebuilt/linux-x64" \
    -DADDITIONAL_LIBRARY_PATHS="${SRC}/dep/prebuilt/linux-x64/lib" \
    -DSoundTouch_ROOT="${SRC}/dep/prebuilt/linux-x64" \
    -DSoundTouch_DIR="${SRC}/dep/prebuilt/linux-x64/lib/cmake/SoundTouch" \
    -DSHADERC_LIBRARY=/usr/lib/x86_64-linux-gnu/libshaderc_combined.a \
    -DBUILD_QT_FRONTEND=ON \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="/opt/hippos/qt/6.11/lib:\$ORIGIN/../lib"

log "Building"
ninja -C "${BUILD}" -j"$(nproc)"

if [[ -x "${BUILD}/bin/duckstation-qt" ]]; then
    cp "${BUILD}/bin/duckstation-qt" "${STAGING}/bin/duckstation"
elif [[ -x "${BUILD}/bin/duckstation-nogui" ]]; then
    cp "${BUILD}/bin/duckstation-nogui" "${STAGING}/bin/duckstation"
else
    die "DuckStation binary was not produced"
fi

chmod +x "${STAGING}/bin/duckstation"
strip "${STAGING}/bin/duckstation" || true

cp -r "${BUILD}/bin/resources" "${STAGING}/bin/"

# Bundle prebuilt runtime libs that the binary's $ORIGIN/../lib rpath expects.
# libcpuinfo.so has no soname versioning in the duckstation prebuilt.
# libsoundtouch.so.2 differs from Debian's libSoundTouch.so.1 (different case + version).
PREBUILT_LIB="${SRC}/dep/prebuilt/linux-x64/lib"
mkdir -p "${STAGING}/lib"
cp "${PREBUILT_LIB}/libcpuinfo.so" "${STAGING}/lib/"
cp "${PREBUILT_LIB}/libsoundtouch.so.2.3.3" "${STAGING}/lib/"
ln -sf libsoundtouch.so.2.3.3 "${STAGING}/lib/libsoundtouch.so.2"
for f in "${PREBUILT_LIB}"/libplutosvg.so.0*; do
    [[ -f "$f" ]] && cp "$f" "${STAGING}/lib/"
done
(cd "${STAGING}/lib" && \
    versioned="$(ls libplutosvg.so.0.* 2>/dev/null | head -1)" && \
    [[ -n "${versioned}" ]] && ln -sf "${versioned}" libplutosvg.so.0 || true)

find /usr/lib/x86_64-linux-gnu -name "libshaderc_shared.so*" \( -type f -o -type l \) | while read -r f; do
    cp -P "$f" "${STAGING}/lib/"
done

write_artifact_version "${STAGING}" "$(git -C "${SRC}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
