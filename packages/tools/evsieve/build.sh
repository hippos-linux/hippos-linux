#!/usr/bin/env bash
# evsieve: input-event remapper that pad2key drives to turn arcade encoders
# (keyboard-mode boards such as Ultimarc I-PAC) into virtual gamepads.
# Not packaged by Debian. Links against libevdev.so.2 (libevdev2 at runtime).
# Pinned to a main-branch commit: pad2key's --output device-id= clause isn't in
# any release yet (1.4.0 rejects it).
set -euo pipefail

source "/work/build/common.sh"

NAME='evsieve'
REPO='https://github.com/KarsMulder/evsieve'
COMMIT="${EVSIEVE_COMMIT:-2b1bcd046829db69617f2a47d8d554f20cd0ec08}"

WORK_ROOT="${WORK_ROOT:-/work/work/tools}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/${ARCH}/tools/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ "$(git -C "${SRC}" rev-parse HEAD 2>/dev/null)" != "${COMMIT}" ]]; then
    rm -rf "${SRC}"
    git init -q "${SRC}"
    git -C "${SRC}" fetch -q --depth=1 "${REPO}" "${COMMIT}"
    git -C "${SRC}" checkout -q FETCH_HEAD
fi

log "Building ${COMMIT}"
cargo build --release --locked --manifest-path "${SRC}/Cargo.toml"

rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin"
install -m755 "$(cargo_release_dir "${SRC}")/evsieve" "${STAGING}/bin/evsieve"
"${STRIP:-strip}" "${STAGING}/bin/evsieve"
printf '%s\n' "${COMMIT}" > "${STAGING}/version"

log "Done. Artifact at ${STAGING}"
