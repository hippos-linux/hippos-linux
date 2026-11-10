# Sourced by the build.sh of PCSX2 and its forks. Set NAME, REPO, TAG and
# STAGED_BIN (the staged binary name) before sourcing; optionally BUILT_BIN
# (the binary CMake produces, default pcsx2-qt) and EXTRA_CMAKE_ARGS (array).
# Every *.patch in packages/emulators/<NAME>/ is applied to the source.

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
DEPS_ROOT="${WORK_ROOT}/${NAME}/deps"

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

for patch in /work/packages/emulators/"${NAME}"/*.patch; do
    [[ -e "${patch}" ]] || continue
    if ! git -C "${SRC}" apply --reverse --check "${patch}" >/dev/null 2>&1; then
        log "Applying $(basename "${patch}")"
        git -C "${SRC}" apply "${patch}"
    fi
done

source "/work/build/qt-env.sh"

DEPS_SCRIPT="${SRC}/.github/workflows/scripts/linux/build-dependencies-qt.sh"

pinned_dep_version() {
    sed -n "s/^$1=//p" "${DEPS_SCRIPT}"
}

pinned_dep_sha256() {
    awk -v t="$1" '$2 == t {print $1}' "${DEPS_SCRIPT}"
}

# fetch_pinned_dep <dir> <VAR> <tarball pattern as written in the deps script> <url with @V@ for the version>
fetch_pinned_dep() {
    local dir="$1" var="$2" pattern="$3" url_template="$4"
    local version sha tarball
    version="$(pinned_dep_version "${var}")"
    sha="$(pinned_dep_sha256 "${pattern}")"
    [[ -n "${version}" && -n "${sha}" ]] || die "Could not read ${var} pin from ${DEPS_SCRIPT}"
    if [[ "$(cat "${dir}/.hippos-version" 2>/dev/null)" == "${version}" ]]; then
        return
    fi
    log "Fetching ${var} ${version}"
    tarball="${DEPS_ROOT}/${var}-${version}.tar.gz"
    rm -rf "${dir}"
    mkdir -p "${dir}"
    curl -fsSL -o "${tarball}" "${url_template//@V@/${version}}"
    echo "${sha}  ${tarball}" | sha256sum --check --strict
    tar -xzf "${tarball}" -C "${dir}" --strip-components=1
    rm -f "${tarball}"
    echo "${version}" > "${dir}/.hippos-version"
}

# build_dep <name> <extra cmake args...>
build_dep() {
    local name="$1"; shift
    rm -rf "${DEPS_ROOT}/${name}/build"
    cmake -S "${DEPS_ROOT}/${name}/source" -B "${DEPS_ROOT}/${name}/build" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="${DEPS_ROOT}/${name}/install" \
        "$@"
    cmake --build "${DEPS_ROOT}/${name}/build" -j"$(nproc)"
    cmake --install "${DEPS_ROOT}/${name}/build"
}

mkdir -p "${DEPS_ROOT}"

fetch_pinned_dep "${DEPS_ROOT}/kddockwidgets/source" KDDOCKWIDGETS 'KDDockWidgets-$KDDOCKWIDGETS.tar.gz' \
    'https://github.com/KDAB/KDDockWidgets/archive/v@V@/KDDockWidgets-@V@.tar.gz'
fetch_pinned_dep "${DEPS_ROOT}/plutovg/source" PLUTOVG 'plutovg-$PLUTOVG.tar.gz' \
    'https://github.com/sammycage/plutovg/archive/v@V@/plutovg-@V@.tar.gz'
fetch_pinned_dep "${DEPS_ROOT}/plutosvg/source" PLUTOSVG 'plutosvg-$PLUTOSVG.tar.gz' \
    'https://github.com/sammycage/plutosvg/archive/v@V@/plutosvg-@V@.tar.gz'
fetch_pinned_dep "${DEPS_ROOT}/rapidyaml/source" RAPIDYAML 'rapidyaml-$RAPIDYAML-src.tgz' \
    'https://github.com/biojppm/rapidyaml/releases/download/v@V@/rapidyaml-@V@-src.tgz'

KDDW_PREFIX="${DEPS_ROOT}/kddockwidgets/install"
PLUTOVG_PREFIX="${DEPS_ROOT}/plutovg/install"
PLUTOSVG_PREFIX="${DEPS_ROOT}/plutosvg/install"
RYML_PREFIX="${DEPS_ROOT}/rapidyaml/install"

build_dep kddockwidgets \
    -DCMAKE_PREFIX_PATH="${QT_ROOT}" \
    -DKDDockWidgets_QT6=ON \
    -DKDDockWidgets_FRONTENDS="qtwidgets" \
    -DKDDockWidgets_EXAMPLES=OFF \
    -DKDDockWidgets_TESTS=OFF \
    -DBUILD_SHARED_LIBS=ON
build_dep plutovg -DBUILD_SHARED_LIBS=OFF
build_dep plutosvg -DCMAKE_PREFIX_PATH="${PLUTOVG_PREFIX}" -DBUILD_SHARED_LIBS=OFF
build_dep rapidyaml -DBUILD_SHARED_LIBS=OFF

SHADERC_LIBRARY="/usr/lib/${GNU_ARCH}/libshaderc_combined.a"
SHADERC_INCLUDE_DIR="/usr/include"
if [[ "${CROSS_BUILD}" -eq 1 ]]; then
    log "Unpacking libshaderc-dev${DEB_TARGET_SUFFIX} headers"
    SHADERC_ROOT="${DEPS_ROOT}/shaderc"
    rm -rf "${SHADERC_ROOT}"
    mkdir -p "${SHADERC_ROOT}"
    apt-get update -qq
    (cd "${SHADERC_ROOT}" && apt-get download "libshaderc-dev${DEB_TARGET_SUFFIX}")
    dpkg-deb -x "${SHADERC_ROOT}"/libshaderc-dev_*.deb "${SHADERC_ROOT}"
    SHADERC_LIBRARY="/usr/lib/${GNU_ARCH}/libshaderc.so.1"
    SHADERC_INCLUDE_DIR="${SHADERC_ROOT}/usr/include"
fi

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
    -DCMAKE_PREFIX_PATH="${QT_ROOT};${PLUTOVG_PREFIX};${PLUTOSVG_PREFIX};${KDDW_PREFIX};${RYML_PREFIX}" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    -DCMAKE_INSTALL_RPATH="${QT_RPATH}:\$ORIGIN/../lib" \
    -DSHADERC_LIBRARY="${SHADERC_LIBRARY}" \
    -DSHADERC_INCLUDE_DIR="${SHADERC_INCLUDE_DIR}" \
    -DBUILD_SHARED_LIBS=OFF \
    -DDISABLE_ADVANCE_SIMD=ON \
    -DENABLE_TESTS=OFF \
    -DUSE_SYSTEM_LIBS=AUTO \
    -DUSE_OPENGL=ON \
    -DUSE_VULKAN=ON \
    -DWAYLAND_API=OFF \
    -DX11_API=ON \
    "${EXTRA_CMAKE_ARGS[@]+"${EXTRA_CMAKE_ARGS[@]}"}"

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

BUILT_BIN="${BUILT_BIN:-pcsx2-qt}"
[[ -x "${BUILD}/bin/${BUILT_BIN}" ]] || die "${BUILT_BIN} binary was not produced"

cp "${BUILD}/bin/${BUILT_BIN}" "${STAGING}/bin/${STAGED_BIN}"

log "Staging runtime data directories alongside binary"
for dir in resources translations; do
    src="${BUILD}/bin/${dir}"
    [[ -d "${src}" ]] && rsync -a "${src}/" "${STAGING}/bin/${dir}/" \
        && log "Staged bin/${dir}/" || log "Warning: ${dir}/ not found in build"
done

mkdir -p "${STAGING}/lib"
find "${DEPS_ROOT}/kddockwidgets/build/lib" -name "libkddockwidgets*.so*" \( -type f -o -type l \) | while read -r f; do
    cp -P "$f" "${STAGING}/lib/"
done
