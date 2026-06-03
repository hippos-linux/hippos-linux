#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='joycond'
REPO='https://github.com/DanielOgorchock/joycond.git'
TAG="${JOYCOND_TAG:-$(github_latest_tag "${REPO}")}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${TAG}"
    git clone --depth=1 --branch "${TAG}" "${REPO}" "${SRC}"
fi

mkdir -p "${BUILD}" "${STAGING}/bin" "${STAGING}/lib/systemd/system" "${STAGING}/lib/udev/rules.d"

log "Configuring with cmake"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

log "Staging"
cp "${BUILD}/joycond" "${STAGING}/bin/joycond"
strip "${STAGING}/bin/joycond"

[[ -f "${SRC}/systemd/joycond.service" ]] && cp "${SRC}/systemd/joycond.service" "${STAGING}/lib/systemd/system/joycond.service"
for rules_file in "${SRC}/udev/"*.rules; do
    [[ -f "${rules_file}" ]] && cp "${rules_file}" "${STAGING}/lib/udev/rules.d/"
done

log "Done. Artifact at ${STAGING}"
