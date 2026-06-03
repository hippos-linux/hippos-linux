#!/usr/bin/env bash
set -euo pipefail

FRONTEND_NAME="emulationstation"
ES_BRANCH="${ES_BRANCH:-hippos}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/frontend}"
SOURCE_DIR="${WORK_ROOT}/${FRONTEND_NAME}/source"
BUILD_DIR="${WORK_ROOT}/${FRONTEND_NAME}/build"
STAGING_DIR="${ARTIFACT_ROOT}/frontend/${FRONTEND_NAME}"
ES_LOCAL="${REPO_ROOT}/src/frontend/emulationstation"

log() { printf '[frontend:%s] %s\n' "${FRONTEND_NAME}" "$*"; }

log "Cloning hippos-emulationstation from local tree (${ES_BRANCH})"
rm -rf "${SOURCE_DIR}" "${BUILD_DIR}"
mkdir -p "${SOURCE_DIR}" "${BUILD_DIR}"
git config --global --add safe.directory '*'
git clone --recurse-submodules --branch "${ES_BRANCH}" "${ES_LOCAL}" "${SOURCE_DIR}"

VERSION_FILE="${REPO_ROOT}/overlays/rootfs/usr/share/hippos/version"
OS_VERSION="$(tr -d '[:space:]' < "${VERSION_FILE}" 2>/dev/null || true)"

log "Configuring (HippOS version: ${OS_VERSION:-unknown})"
SCREENSCRAPER_DEV_LOGIN="${SCREENSCRAPER_DEV_LOGIN:-devid=batoceralinux&devpassword=omvIrirRPuY}"
SCREENSCRAPER_SOFTNAME="${SCREENSCRAPER_SOFTNAME:-HippOS}"

cmake -S "${SOURCE_DIR}" -B "${BUILD_DIR}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DGL=on \
    -DENABLE_PULSE=on \
    -DDISABLE_KODI=on \
    -DHIPPOS=on \
    ${OS_VERSION:+-DHIPPOS_VERSION="${OS_VERSION}"} \
    -DSCREENSCRAPER_DEV_LOGIN="${SCREENSCRAPER_DEV_LOGIN}" \
    -DSCREENSCRAPER_SOFTNAME="${SCREENSCRAPER_SOFTNAME}"

log "Building"
cmake --build "${BUILD_DIR}" -- -j"$(nproc)"

log "Staging"
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"
DESTDIR="${STAGING_DIR}" cmake --install "${BUILD_DIR}"

log "Done — artifact at ${STAGING_DIR}"
