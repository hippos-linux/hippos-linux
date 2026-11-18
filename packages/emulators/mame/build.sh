#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='mame'
REPO='https://github.com/antonioginer/GroovyMAME'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

unset ARCH

if [[ "${CROSS_BUILD}" -eq 1 ]]; then
    make -C "${SRC}" -j"$(nproc)" NOWERROR=1 \
        TARGETOS=linux \
        PLATFORM=arm64 \
        ARCHITECTURE= \
        NOASM=1 \
        PTR64=1 \
        OVERRIDE_CC="${GNU_ARCH}-gcc" \
        OVERRIDE_CXX="${GNU_ARCH}-g++" \
        OVERRIDE_LD="${GNU_ARCH}-g++" \
        OVERRIDE_AR="${GNU_ARCH}-ar"
else
    make -C "${SRC}" -j"$(nproc)" TOOLS=1 NOWERROR=1
fi

mkdir -p "${STAGING}/bin"
staged=0
while IFS= read -r -d '' executable; do
    install -m 0755 "${executable}" "${STAGING}/bin/"
    staged=$((staged + 1))
done < <(find "${SRC}" -maxdepth 1 -type f -perm /111 -print0)

if [[ "${staged}" -eq 0 ]]; then
    log "No executable artifacts found in ${SRC}"
    exit 1
fi

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
