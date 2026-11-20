#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='gopher64'
REPO='https://github.com/gopher64/gopher64'
TAG="$(github_latest_tag "${REPO}")"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

if [[ "${CROSS_BUILD}" -eq 0 ]]; then
    export CC=clang CXX=clang++
fi

log "Building gopher64 ${TAG}"
cargo build --release --manifest-path "${SRC}/Cargo.toml"

rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin"
install -m755 "$(cargo_release_dir "${SRC}")/gopher64" "${STAGING}/bin/gopher64"
"${STRIP:-strip}" "${STAGING}/bin/gopher64"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
