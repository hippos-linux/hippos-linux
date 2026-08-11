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
STAGING="${ARTIFACT_ROOT}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${TAG}"
    git clone --depth=1 --branch "${TAG}" "${REPO}" "${SRC}"
fi

# Build only asusd/asusctl/asus-shutdown/asusd-user — deliberately not
# rog-control-center (the Slint GUI). Its deps (libxkbcommon-dev etc) aren't
# in the bulk image and HippOS's own settings menu, not a bundled desktop
# app, is the intended control surface here. The daemon exposes everything
# over D-Bus regardless (org.asuslinux.Daemon) — nothing is lost, this just
# means driving it via `asusctl` instead of the GUI for now.
log "Building asusd/asusctl/asus-shutdown/asusd-user"
cd "${SRC}"
cargo build --release -p asusd -p asusctl -p asus-shutdown -p asusd-user

log "Installing to staging (via upstream Makefile, prefix=/usr)"
rm -rf "${STAGING}"
make -C "${SRC}" DESTDIR="${STAGING}" \
    install-asusd install-asusctl install-asus-shutdown install-asusd_user \
    install-data-asusd

# install-data-asusd_user is declared .PHONY but has no recipe upstream —
# asusd-user.service is never actually installed by any Makefile target.
# Stage it ourselves to match the other three services.
install -Dm644 "${SRC}/data/asusd-user.service" \
    "${STAGING}/usr/lib/systemd/system/asusd-user.service"

log "Stripping binaries"
for bin in asusd asusctl asus-shutdown asusd-user; do
    strip -s "${STAGING}/usr/bin/${bin}" 2>/dev/null || true
done

log "Done. Artifact at ${STAGING}"
