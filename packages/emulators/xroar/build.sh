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

TARBALL="${BUILD}/xroar-${VERSION}.tar.gz"
if [[ ! -f "${TARBALL}" ]]; then
    log "Downloading xroar-${VERSION}.tar.gz"
    mkdir -p "${BUILD}"
    curl -fL "${TARBALL_URL}" -o "${TARBALL}"
fi
# Extract fresh each run so a new VERSION actually replaces the old source.
rm -rf "${SRC}"
mkdir -p "${SRC}"
tar xf "${TARBALL}" -C "${SRC}" --strip-components=1

mkdir -p "${STAGING}/bin"
cd "${SRC}"
_host_args=()
[[ "${ARCH:-amd64}" == "arm64" ]] && [[ "$(uname -m)" == "x86_64" ]] && \
    _host_args=(--host=aarch64-linux-gnu --build=x86_64-linux-gnu)
./configure --prefix="${EMULATOR_RUNTIME_ROOT}/${NAME}" "${_host_args[@]}"
# doc/ is skipped: the release tarball's rules for it need manpage-header and
# xroar-man.html, which it doesn't ship.
make -j"$(nproc)" SUBDIRS="portalib src"
install_staged "${NAME}" "${STAGING}" "${BUILD}/destdir" make install SUBDIRS="portalib src"

write_artifact_version "${STAGING}" "${VERSION}"
log "Done. Artifact at ${STAGING}"
