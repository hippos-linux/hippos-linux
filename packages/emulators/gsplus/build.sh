#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='gsplus'
REPO='https://github.com/applemu/gsplus'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

git config --global --add safe.directory "${SRC}" 2>/dev/null || true

mkdir -p "${STAGING}/bin"

(
    cd "${SRC}/src"
    cp vars_x86linux_sdl2 vars
    make -j"$(nproc)" gsplus
)

cp "${SRC}/gsplus" "${STAGING}/bin/gsplus"
chmod +x "${STAGING}/bin/gsplus"

# Stage supporting data (ROM images, config templates)
for item in assets lib; do
    [[ -d "${SRC}/${item}" ]] && rsync -a "${SRC}/${item}/" "${STAGING}/${item}/" || true
done

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
