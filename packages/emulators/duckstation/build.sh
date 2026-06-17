#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='duckstation'
REPO='https://github.com/stenzek/duckstation.git'
REF="${DUCKSTATION_REF:-master}"

case "${ARCH:-amd64}" in
    arm64) _ds_arch="aarch64"; _ds_deps_suffix="linux-aarch64" ;;
    *)     _ds_arch="x64";     _ds_deps_suffix="linux-x64"     ;;
esac
DEPS_REPO="https://github.com/duckstation/dependencies/releases/latest/download/deps-${_ds_deps_suffix}.tar.xz"

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

if [[ ! -f "${SRC}/dep/prebuilt/.deps-${_ds_deps_suffix}.done" ]]; then
    if [[ "${ARCH:-amd64}" == "arm64" ]] && [[ "$(uname -m)" == "x86_64" ]]; then
        # No prebuilt arm64 tarball available from duckstation/dependencies.
        # Use the upstream cross-compilation dep build script instead.
        CROSS_DEPS_DIR="${WORK_ROOT}/${NAME}/cross-deps-arm64"
        CROSS_DEPS_SCRIPT="${WORK_ROOT}/${NAME}/build-dependencies-linux-cross.sh"

        if [[ ! -f "${CROSS_DEPS_DIR}/.done" ]]; then
            log "Downloading cross-dep build script"
            curl -fL \
                "https://raw.githubusercontent.com/duckstation/dependencies/refs/heads/master/build-dependencies-linux-cross.sh" \
                -o "${CROSS_DEPS_SCRIPT}"
            chmod +x "${CROSS_DEPS_SCRIPT}"

            # Strip the Qt build/install sections from the script — we already
            # have a custom arm64 Qt 6.11 mounted at ${QT_ROOT}. Skip from any
            # "echo "Building/Installing Qt..." line through the next non-Qt
            # section echo so the script only builds the non-Qt deps
            # (cpuinfo, soundtouch, plutosvg, shaderc, SDL, etc.).
            python3 - "${CROSS_DEPS_SCRIPT}" << 'PYEOF'
import sys, re
lines = open(sys.argv[1]).readlines()
out, skip = [], False
for line in lines:
    if re.match(r'\s*echo "(?:Building|Installing) Qt', line):
        skip = True
    elif skip and re.match(r'\s*echo "(?:Building|Installing) ', line) and 'Qt' not in line:
        skip = False
    if not skip:
        out.append(line)
open(sys.argv[1], 'w').writelines(out)
PYEOF

            mkdir -p "${CROSS_DEPS_DIR}"
            log "Building arm64 dependencies from source (this takes a while)"
            # SYSROOTDIR=/: arm64 multiarch libs live at /usr/lib/aarch64-linux-gnu/
            # HOSTDIR unused now (Qt sections stripped), but arg is still required
            "${CROSS_DEPS_SCRIPT}" \
                /opt/hippos/qt/6.11-host \
                arm64 \
                / \
                "${CROSS_DEPS_DIR}"
            touch "${CROSS_DEPS_DIR}/.done"
        fi

        # Symlink cross-built deps where duckstation cmake expects prebuilt/linux-aarch64
        ln -sfn "${CROSS_DEPS_DIR}" "${SRC}/dep/prebuilt/${_ds_deps_suffix}"
        touch "${SRC}/dep/prebuilt/.deps-${_ds_deps_suffix}.done"
    else
        log "Downloading DuckStation deps-${_ds_deps_suffix}"
        if ! curl -fL "${DEPS_REPO}" -o "${WORK_ROOT}/${NAME}/deps-${_ds_deps_suffix}.tar.xz"; then
            log "Prebuilt deps unavailable for ${_ds_deps_suffix} (${DEPS_REPO}); skipping"
            exit 0
        fi

        log "Extracting DuckStation prebuilt dependencies"
        tar -xJf "${WORK_ROOT}/${NAME}/deps-${_ds_deps_suffix}.tar.xz" -C "${SRC}/dep/prebuilt"
        touch "${SRC}/dep/prebuilt/.deps-${_ds_deps_suffix}.done"
    fi
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
    -DCMAKE_PREFIX_PATH="${QT_ROOT};${SRC}/dep/prebuilt/${_ds_deps_suffix}" \
    -DADDITIONAL_LIBRARY_PATHS="${SRC}/dep/prebuilt/${_ds_deps_suffix}/lib" \
    -DSoundTouch_ROOT="${SRC}/dep/prebuilt/${_ds_deps_suffix}" \
    -DSoundTouch_DIR="${SRC}/dep/prebuilt/${_ds_deps_suffix}/lib/cmake/SoundTouch" \
    -DSHADERC_LIBRARY=/usr/lib/${GNU_ARCH}/libshaderc_combined.a \
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
PREBUILT_LIB="${SRC}/dep/prebuilt/${_ds_deps_suffix}/lib"
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

write_artifact_version "${STAGING}" "$(git -C "${SRC}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
