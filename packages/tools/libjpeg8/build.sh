#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='libjpeg8'
VERSION="${LIBJPEG_TURBO_VERSION:-3.1.2}"
URL="https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/${VERSION}/libjpeg-turbo-${VERSION}.tar.gz"

WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
SRC="${WORK_ROOT}/${NAME}/libjpeg-turbo-${VERSION}"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/${ARCH}/tools/${NAME}"
LIB_DIR="usr/lib/hippos/sinden"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -f "${SRC}/CMakeLists.txt" ]]; then
    rm -rf "${WORK_ROOT:?}/${NAME}"
    mkdir -p "${WORK_ROOT}/${NAME}"
    curl -fsSL "${URL}" | tar -xz -C "${WORK_ROOT}/${NAME}"
fi

log "Building libjpeg-turbo ${VERSION} with the libjpeg 8 ABI"
rm -rf "${BUILD}"
cmake -S "${SRC}" -B "${BUILD}" -DCMAKE_BUILD_TYPE=Release -DWITH_JPEG8=1 -DENABLE_STATIC=0 -DWITH_TURBOJPEG=0
cmake --build "${BUILD}" -j"$(nproc)"

rm -rf "${STAGING}"
mkdir -p "${STAGING}/${LIB_DIR}"
cp -P "${BUILD}"/libjpeg.so.8* "${STAGING}/${LIB_DIR}/"
"${STRIP:-strip}" "${STAGING}/${LIB_DIR}"/libjpeg.so.8.*
printf '%s\n' "${VERSION}" > "${STAGING}/version"

log "Done. Artifact at ${STAGING}"
