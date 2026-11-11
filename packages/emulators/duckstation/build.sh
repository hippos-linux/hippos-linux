#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='duckstation'
REPO='https://github.com/duckstation/old-releases.git'
REF="${DUCKSTATION_REF:-v0.1-7371}"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build-release"
DEPS_SRC="${WORK_ROOT}/${NAME}/deps-src"
DEPS_PREFIX="${WORK_ROOT}/${NAME}/deps-${ARCH}"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

CPUINFO=7524ad504fdcfcf75a18a133da6abd75c5d48053
DISCORD_RPC=144f3a3f1209994d8d9e8a87964a989cb9911c1e
SHADERC=feb2460bf3a504d67011246edeb810c45ea58826
SOUNDTOUCH=463ade388f3a51da078dc9ed062bf28e4ba29da7
SPIRV_CROSS=vulkan-sdk-1.3.290.0

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

fetch_stenzek_dep() {
    local project="$1" commit="$2" dest="${DEPS_SRC}/$1-$2"
    [[ -d "${dest}" ]] && return 0
    mkdir -p "${DEPS_SRC}"
    curl -fsSL "https://github.com/stenzek/${project}/archive/${commit}.tar.gz" | tar -xz -C "${DEPS_SRC}"
}

build_dep() {
    local src="$1"; shift
    rm -rf "${src}/build"
    cmake -S "${src}" -B "${src}/build" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_PREFIX_PATH="${DEPS_PREFIX}" \
        -DCMAKE_INSTALL_PREFIX="${DEPS_PREFIX}" \
        "$@"
    cmake --build "${src}/build" -j"$(nproc)"
    cmake --install "${src}/build"
}

build_deps() {
    local stamp="${DEPS_PREFIX}/.deps-${CPUINFO}-${DISCORD_RPC}-${SHADERC}-${SOUNDTOUCH}-${SPIRV_CROSS}"
    [[ -f "${stamp}" ]] && return 0
    rm -rf "${DEPS_PREFIX}"

    fetch_stenzek_dep cpuinfo "${CPUINFO}"
    fetch_stenzek_dep discord-rpc "${DISCORD_RPC}"
    fetch_stenzek_dep shaderc "${SHADERC}"
    fetch_stenzek_dep soundtouch "${SOUNDTOUCH}"
    [[ -d "${DEPS_SRC}/SPIRV-Cross-${SPIRV_CROSS}" ]] || \
        git clone -q --depth 1 -b "${SPIRV_CROSS}" https://github.com/KhronosGroup/SPIRV-Cross "${DEPS_SRC}/SPIRV-Cross-${SPIRV_CROSS}"

    log "Building shaderc"
    build_dep "${DEPS_SRC}/shaderc-${SHADERC}" \
        -DSHADERC_SKIP_TESTS=ON -DSHADERC_SKIP_EXAMPLES=ON -DSHADERC_SKIP_COPYRIGHT_CHECK=ON
    log "Building SPIRV-Cross"
    build_dep "${DEPS_SRC}/SPIRV-Cross-${SPIRV_CROSS}" \
        -DSPIRV_CROSS_SHARED=ON -DSPIRV_CROSS_STATIC=OFF -DSPIRV_CROSS_CLI=OFF \
        -DSPIRV_CROSS_ENABLE_TESTS=OFF -DSPIRV_CROSS_ENABLE_GLSL=ON -DSPIRV_CROSS_ENABLE_HLSL=OFF \
        -DSPIRV_CROSS_ENABLE_MSL=OFF -DSPIRV_CROSS_ENABLE_CPP=OFF -DSPIRV_CROSS_ENABLE_REFLECT=OFF \
        -DSPIRV_CROSS_ENABLE_C_API=ON -DSPIRV_CROSS_ENABLE_UTIL=ON
    log "Building cpuinfo"
    build_dep "${DEPS_SRC}/cpuinfo-${CPUINFO}" \
        -DCPUINFO_LIBRARY_TYPE=shared -DCPUINFO_RUNTIME_TYPE=shared -DCPUINFO_LOG_LEVEL=error \
        -DCPUINFO_LOG_TO_STDIO=ON -DCPUINFO_BUILD_TOOLS=OFF -DCPUINFO_BUILD_UNIT_TESTS=OFF \
        -DCPUINFO_BUILD_MOCK_TESTS=OFF -DCPUINFO_BUILD_BENCHMARKS=OFF -DUSE_SYSTEM_LIBS=ON
    log "Building discord-rpc"
    build_dep "${DEPS_SRC}/discord-rpc-${DISCORD_RPC}" -DBUILD_SHARED_LIBS=ON
    log "Building soundtouch"
    build_dep "${DEPS_SRC}/soundtouch-${SOUNDTOUCH}" -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON

    touch "${stamp}"
}

clone_source "${REPO}" "${REF}" "${SRC}" --submodules

sed -i -e 's/^find_package(Qt6 6.7.2 COMPONENTS Core Gui Widgets LinguistTools REQUIRED)$/find_package(Qt6 6.7.2 COMPONENTS Core Gui GuiPrivate Widgets LinguistTools REQUIRED)/' \
       -e 's/ Qt6::Core Qt6::Gui Qt6::Widgets)$/ Qt6::Core Qt6::Gui Qt6::GuiPrivate Qt6::Widgets)/' \
    "${SRC}/src/duckstation-qt/CMakeLists.txt"
grep -q 'Qt6::GuiPrivate Qt6::Widgets' "${SRC}/src/duckstation-qt/CMakeLists.txt" || die "Qt GuiPrivate link edit did not apply"
sed -i 's/const bool visible = force_visible || !hide_window || !has_window;/const bool visible = force_visible || !hide_window || (!has_window \&\& !QtHost::InNoGUIMode());/' \
    "${SRC}/src/duckstation-qt/mainwindow.cpp"
grep -q '!has_window && !QtHost::InNoGUIMode()' "${SRC}/src/duckstation-qt/mainwindow.cpp" || die "nogui main window edit did not apply"

source "/work/build/qt-env.sh"

build_deps

rm -rf "${BUILD}" "${STAGING}"
mkdir -p "${STAGING}/bin" "${STAGING}/lib"

DUCKSTATION_RPATH="${QT_RPATH}:${EMULATOR_RUNTIME_ROOT}/${NAME}/lib"

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_EXE_LINKER_FLAGS_INIT="-fuse-ld=lld -Wl,-rpath,${DUCKSTATION_RPATH}" \
    -DCMAKE_MODULE_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_SHARED_LINKER_FLAGS_INIT="-fuse-ld=lld" \
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON \
    -DCMAKE_PREFIX_PATH="${QT_ROOT};${DEPS_PREFIX}" \
    -DADDITIONAL_LIBRARY_PATHS="${DEPS_PREFIX}/lib" \
    -DBUILD_QT_FRONTEND=ON

log "Building"
ninja -C "${BUILD}" -j"$(nproc)"

[[ -x "${BUILD}/bin/duckstation-qt" ]] || die "DuckStation binary was not produced"
cp "${BUILD}/bin/duckstation-qt" "${STAGING}/bin/duckstation"
cp -r "${BUILD}/bin/resources" "${BUILD}/bin/translations" "${STAGING}/bin/"

for lib in libshaderc_shared.so libspirv-cross-c-shared.so.0 libcpuinfo.so libdiscord-rpc.so libsoundtouch.so.2; do
    cp -L "${DEPS_PREFIX}/lib/${lib}" "${STAGING}/lib/${lib}"
done

install -Dm644 "${SRC}/LICENSE" "${STAGING}/share/doc/duckstation/LICENSE"

write_artifact_version "${STAGING}" "${REF}"
log "Done. Artifact at ${STAGING}"
