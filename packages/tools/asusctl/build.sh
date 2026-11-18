#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='asusctl'
REPO='https://github.com/OpenGamingCollective/asusctl.git'
TAG="${ASUSCTL_TAG:-6.3.11}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/${ARCH}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${TAG}"
    git clone --depth=1 --branch "${TAG}" "${REPO}" "${SRC}"
fi

log "Building asusd/asusctl/asus-shutdown/asusd-user"
cd "${SRC}"
cargo build --release -p asusd -p asusctl -p asus-shutdown -p asusd-user

log "Installing to staging (via upstream Makefile, prefix=/usr)"
rm -rf "${STAGING}"
make -C "${SRC}" DESTDIR="${STAGING}" \
    install-asusd install-asusctl install-asus-shutdown install-asusd_user \
    install-data-asusd

install -Dm644 "${SRC}/data/asusd-user.service" \
    "${STAGING}/usr/lib/systemd/system/asusd-user.service"

log "Stripping binaries"
for bin in asusd asusctl asus-shutdown asusd-user; do
    strip -s "${STAGING}/usr/bin/${bin}" 2>/dev/null || true
done

log "Done. Artifact at ${STAGING}"
