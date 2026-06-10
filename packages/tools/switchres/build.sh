#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='switchres'
REPO='https://github.com/antonioginer/switchres.git'
TAG="${SWITCHRES_TAG:-v2.2.2}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
SRC="${WORK_ROOT}/${NAME}/source"
INSTALL_DEST="${WORK_ROOT}/${NAME}/install"
STAGING="${ARTIFACT_ROOT}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

log "Installing build deps"
apt-get update -qq
apt-get install -y --no-install-recommends \
    libxrandr-dev libx11-dev libdrm-dev

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${TAG}"
    git clone --depth=1 --branch "${TAG}" "${REPO}" "${SRC}"
fi

mkdir -p "${INSTALL_DEST}" "${STAGING}/bin" "${STAGING}/lib" "${STAGING}/include"

log "Building"
make -C "${SRC}" -j"$(nproc)"

log "Installing to staging prefix"
make -C "${SRC}" install DESTDIR="${INSTALL_DEST}" PREFIX=/usr

log "Staging binary"
# The makefile install target omits the binary; copy it directly from source.
install -m 755 "${SRC}/switchres" "${STAGING}/bin/switchres"
strip "${STAGING}/bin/switchres"

log "Staging shared library"
find "${INSTALL_DEST}/usr/lib" -name 'libswitchres*.so*' | while IFS= read -r f; do
    cp -a "${f}" "${STAGING}/lib/"
done
for f in "${STAGING}/lib/"libswitchres*.so*; do
    [[ -f "${f}" && ! -L "${f}" ]] && strip --strip-debug "${f}" || true
done

log "Staging headers"
find "${INSTALL_DEST}/usr/include" -name '*.h' | while IFS= read -r h; do
    cp "${h}" "${STAGING}/include/"
done

log "Done. Artifact at ${STAGING}"
log "  bin: $(ls "${STAGING}/bin/")"
log "  lib: $(ls "${STAGING}/lib/")"
log "  include: $(ls "${STAGING}/include/")"
