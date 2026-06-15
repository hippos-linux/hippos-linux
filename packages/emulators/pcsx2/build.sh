#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='pcsx2'
REPO='https://github.com/pcsx2/pcsx2.git'
TAG="${PCSX2_TAG:-$(github_latest_tag "${REPO}")}"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

DEPS_ROOT="${WORK_ROOT}/${NAME}/deps"

KDDW_SRC="${DEPS_ROOT}/kddockwidgets/source"
KDDW_BUILD="${DEPS_ROOT}/kddockwidgets/build"
KDDW_PREFIX="${DEPS_ROOT}/kddockwidgets/install"

PLUTOVG_SRC="${DEPS_ROOT}/plutovg/source"
PLUTOVG_BUILD="${DEPS_ROOT}/plutovg/build"
PLUTOVG_PREFIX="${DEPS_ROOT}/plutovg/install"

PLUTOSVG_SRC="${DEPS_ROOT}/plutosvg/source"
PLUTOSVG_BUILD="${DEPS_ROOT}/plutosvg/build"
PLUTOSVG_PREFIX="${DEPS_ROOT}/plutosvg/install"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ -d "${SRC}/.git" ]]; then
    current_tag="$(git -C "${SRC}" describe --tags --exact-match 2>/dev/null || true)"
    if [[ "${current_tag}" != "${TAG}" ]]; then
        log "Tag mismatch (have '${current_tag}', need '${TAG}'), re-cloning"
        rm -rf "${SRC}"
    fi
fi

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${TAG}"
    rm -rf "${SRC}"
    git clone --depth=1 --branch "${TAG}" "${REPO}" "${SRC}"
fi

git -C "${SRC}" submodule update --init --recursive

source "/work/build/qt611-env.sh"

# KDDockWidgets-qt6 is not in Trixie repos; build from source
if [[ ! -d "${KDDW_SRC}/.git" ]]; then
    log "Cloning KDDockWidgets"
    git clone --depth=1 --branch 2.3 \
        https://github.com/KDAB/KDDockWidgets.git "${KDDW_SRC}"
fi
rm -rf "${KDDW_BUILD}"
cmake -S "${KDDW_SRC}" -B "${KDDW_BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${KDDW_PREFIX}" \
    -DCMAKE_PREFIX_PATH="${QT_ROOT}" \
    -DKDDockWidgets_QT6=ON \
    -DKDDockWidgets_FRONTENDS="qtwidgets" \
    -DKDDockWidgets_EXAMPLES=OFF \
    -DKDDockWidgets_TESTS=OFF \
    -DBUILD_SHARED_LIBS=ON
cmake --build "${KDDW_BUILD}" -j"$(nproc)"
cmake --install "${KDDW_BUILD}"

if [[ ! -d "${PLUTOVG_SRC}/.git" ]]; then
    log "Cloning plutovg"
    rm -rf "${PLUTOVG_SRC}"
    git clone --depth=1 https://github.com/sammycage/plutovg.git "${PLUTOVG_SRC}"
fi

rm -rf "${PLUTOVG_BUILD}"
cmake -S "${PLUTOVG_SRC}" -B "${PLUTOVG_BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${PLUTOVG_PREFIX}" \
    -DBUILD_SHARED_LIBS=OFF

cmake --build "${PLUTOVG_BUILD}" -j"$(nproc)"
cmake --install "${PLUTOVG_BUILD}"

if [[ ! -d "${PLUTOSVG_SRC}/.git" ]]; then
    log "Cloning plutosvg"
    rm -rf "${PLUTOSVG_SRC}"
    git clone --depth=1 https://github.com/sammycage/plutosvg.git "${PLUTOSVG_SRC}"
fi

rm -rf "${PLUTOSVG_BUILD}"
cmake -S "${PLUTOSVG_SRC}" -B "${PLUTOSVG_BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${PLUTOSVG_PREFIX}" \
    -DCMAKE_PREFIX_PATH="${PLUTOVG_PREFIX}" \
    -DBUILD_SHARED_LIBS=OFF

cmake --build "${PLUTOSVG_BUILD}" -j"$(nproc)"
cmake --install "${PLUTOSVG_BUILD}"

rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_EXE_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_MODULE_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_SHARED_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_PREFIX_PATH="${QT_ROOT};${PLUTOVG_PREFIX};${PLUTOSVG_PREFIX};${KDDW_PREFIX}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="/opt/hippos/qt/6.11/lib:\$ORIGIN/../lib" \
    -DSHADERC_LIBRARY=/usr/lib/x86_64-linux-gnu/libshaderc_combined.a \
    -DSHADERC_INCLUDE_DIR=/usr/include \
    -DBUILD_SHARED_LIBS=OFF \
    -DDISABLE_ADVANCE_SIMD=ON \
    -DENABLE_TESTS=OFF \
    -DUSE_SYSTEM_LIBS=AUTO \
    -DUSE_OPENGL=ON \
    -DUSE_VULKAN=ON \
    -DWAYLAND_API=OFF \
    -DX11_API=ON

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

if [[ ! -x "${BUILD}/bin/pcsx2-qt" ]]; then
    die "pcsx2-qt binary was not produced"
fi

cp "${BUILD}/bin/pcsx2-qt" "${STAGING}/bin/pcsx2-qt"
strip "${STAGING}/bin/pcsx2-qt" || true

log "Staging runtime data directories alongside binary"
for dir in resources translations; do
    src="${BUILD}/bin/${dir}"
    [[ -d "${src}" ]] && rsync -a "${src}/" "${STAGING}/bin/${dir}/" \
        && log "Staged bin/${dir}/" || log "Warning: ${dir}/ not found in build"
done

# KDDockWidgets shared lib lands in build dir, not install prefix.
# Filename is all-lowercase: libkddockwidgets-qt6.so*
mkdir -p "${STAGING}/lib"
find "${KDDW_BUILD}/lib" -name "libkddockwidgets*.so*" \( -type f -o -type l \) | while read -r f; do
    cp -P "$f" "${STAGING}/lib/"
done
write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
