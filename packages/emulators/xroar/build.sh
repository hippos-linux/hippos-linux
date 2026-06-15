#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='xroar'
VERSION="$(curl -sf 'https://www.6809.org.uk/xroar/dl/' \
    | grep -oP 'xroar-\K[0-9]+\.[0-9]+(?=\.tar)' | sort -V | tail -1)"
TARBALL_URL="https://www.6809.org.uk/xroar/dl/xroar-${VERSION}.tar.gz"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -d "${SRC}" ]] || [[ -z "$(ls -A "${SRC}" 2>/dev/null)" ]]; then
    log "Downloading xroar-${VERSION}.tar.gz"
    mkdir -p "${BUILD}"
    curl -L "${TARBALL_URL}" -o "${BUILD}/xroar-${VERSION}.tar.gz"
    mkdir -p "${SRC}"
    tar xf "${BUILD}/xroar-${VERSION}.tar.gz" -C "${SRC}" --strip-components=1
fi

mkdir -p "${STAGING}/bin"
cd "${SRC}"
_host_args=()
[[ "${ARCH:-amd64}" == "arm64" ]] && [[ "$(uname -m)" == "x86_64" ]] && \
    _host_args=(--host=aarch64-linux-gnu --build=x86_64-linux-gnu)
./configure --prefix="${STAGING}" "${_host_args[@]}"
make -j"$(nproc)"
make install

write_artifact_version "${STAGING}" "${VERSION}"
log "Done. Artifact at ${STAGING}"
