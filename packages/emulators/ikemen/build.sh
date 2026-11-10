#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='ikemen'
REPO='https://github.com/ikemen-engine/Ikemen-GO'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

GO122_DIR="${WORK_ROOT}/go1.22"
GO122_TAR="${WORK_ROOT}/go1.22.9.linux-amd64.tar.gz"
if [[ ! -x "${GO122_DIR}/bin/go" ]]; then
    log "Downloading Go 1.22"
    curl -fL "https://go.dev/dl/go1.22.9.linux-amd64.tar.gz" -o "${GO122_TAR}"
    mkdir -p "${GO122_DIR}"
    tar -xzf "${GO122_TAR}" -C "${GO122_DIR}" --strip-components=1
    rm -f "${GO122_TAR}"
fi

mkdir -p "${STAGING}/bin"
cd "${SRC}"
go_target_env=()
if [[ "${CROSS_BUILD}" -eq 1 ]]; then
    go_target_env=(GOOS=linux GOARCH=arm64 CGO_ENABLED=1 CC="${GNU_ARCH}-gcc" CXX="${GNU_ARCH}-g++")
fi
env "${go_target_env[@]+"${go_target_env[@]}"}" GOEXPERIMENT=arenas "${GO122_DIR}/bin/go" build -o Ikemen_GO ./src/
cp "${SRC}/Ikemen_GO" "${STAGING}/bin/"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
