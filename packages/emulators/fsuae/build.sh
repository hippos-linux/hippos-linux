#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='fsuae'
REPO='https://github.com/FrodeSolheim/fs-uae'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

mkdir -p "${STAGING}/bin"
(
    cd "${SRC}"
    if [[ -f bootstrap ]]; then
        ./bootstrap
    elif [[ ! -f configure ]]; then
        autoreconf -fiv
    fi

    if [[ "${ARCH:-amd64}" == "arm64" ]] && [[ "$(uname -m)" == "x86_64" ]]; then

        CC=gcc CXX=g++ AR=ar ./configure --prefix="${STAGING}"
        make -j"$(nproc)" 2>/dev/null || true

        find gen -maxdepth 1 -type f -perm /111 -exec touch {} + 2>/dev/null || true
        find gen -maxdepth 1 \( -name '*.cpp' -o -name '*.h' -o -name '*.c' \) \
            -exec touch {} + 2>/dev/null || true

        find . -maxdepth 4 -name '*.o' -not -path './gen/*' -delete 2>/dev/null || true
        find . -maxdepth 4 -name '*.a' -not -path './gen/*' -delete 2>/dev/null || true

        ./configure --prefix="${STAGING}" \
            --host=aarch64-linux-gnu --build=x86_64-linux-gnu
        find gen -maxdepth 1 -type f -perm /111 -exec touch {} + 2>/dev/null || true
        find gen -maxdepth 1 \( -name '*.cpp' -o -name '*.h' -o -name '*.c' \) \
            -exec touch {} + 2>/dev/null || true
        make -j"$(nproc)"
    else
        ./configure --prefix="${STAGING}"
        make -j"$(nproc)"
    fi
    make install
)

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
