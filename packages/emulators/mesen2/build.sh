#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='mesen2'
REPO='https://github.com/SourMesen/Mesen2.git'
REF="${MESEN2_REF:-master}"
SHA="${MESEN2_SHA:-b9fa69ddc6d0a331fb103fdb5eef6904305703c2}"
DOTNET_CHANNEL='8.0'

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
DOTNET_ROOT="${WORK_ROOT}/${NAME}/dotnet"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ -d "${SRC}/.git" && "$(git -C "${SRC}" rev-parse HEAD 2>/dev/null)" != "${SHA}" ]]; then
    rm -rf "${SRC}"
fi
if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${SHA:0:12}"
    git clone --depth=1 --branch "${REF}" "${REPO}" "${SRC}"
    if [[ "$(git -C "${SRC}" rev-parse HEAD)" != "${SHA}" ]]; then
        git -C "${SRC}" fetch --depth=1 origin "${SHA}"
        git -C "${SRC}" checkout --quiet "${SHA}"
    fi
fi

if [[ ! -x "${DOTNET_ROOT}/dotnet" ]]; then
    log "Installing the .NET ${DOTNET_CHANNEL} SDK into the work folder"
    curl -fsSL https://dot.net/v1/dotnet-install.sh -o "${WORK_ROOT}/${NAME}/dotnet-install.sh"
    bash "${WORK_ROOT}/${NAME}/dotnet-install.sh" --channel "${DOTNET_CHANNEL}" --install-dir "${DOTNET_ROOT}"
fi
export PATH="${DOTNET_ROOT}:${PATH}" DOTNET_ROOT DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1

log "Building Mesen ${SHA:0:12}"
make -C "${SRC}" -j"$(nproc)" USE_AOT=true

MESEN_BIN="$(find "${SRC}/bin" -path '*/publish/Mesen' -type f | head -1)"
[[ -n "${MESEN_BIN}" ]] || die "Mesen binary not found after build"
rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin"
install -m755 "${MESEN_BIN}" "${STAGING}/bin/mesen"
install -m644 "$(dirname "${MESEN_BIN}")"/*.so "${STAGING}/bin/"

write_artifact_version "${STAGING}" "${SHA:0:12}"
log "Done. Artifact at ${STAGING}"
