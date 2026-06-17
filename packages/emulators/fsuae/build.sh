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
        # genblitter and build68k are code-generator binaries that must execute
        # on the build machine (x86_64). Two-phase approach:
        #   Phase 1: native configure + build to produce gen/ binaries and generated
        #            source files (blitter.cpp, etc.)
        #   Phase 2: cross-configure; touch gen/ outputs so make won't re-run
        #            generators; compile everything else as arm64.

        # Phase 1: native build (ignore errors — only need gen/ outputs)
        CC=gcc CXX=g++ AR=ar ./configure --prefix="${STAGING}"
        make -j"$(nproc)" 2>/dev/null || true

        # Mark native gen binaries and generated sources as up-to-date so the
        # cross-build won't try to rebuild or re-run them.
        find gen -maxdepth 1 -type f -perm /111 -exec touch {} + 2>/dev/null || true
        find gen -maxdepth 1 \( -name '*.cpp' -o -name '*.h' -o -name '*.c' \) \
            -exec touch {} + 2>/dev/null || true

        # Delete x86_64 object files outside gen/ so they recompile as arm64.
        # Keep gen/*.o so make sees gen/genblitter as up-to-date.
        find . -maxdepth 4 -name '*.o' -not -path './gen/*' -delete 2>/dev/null || true
        find . -maxdepth 4 -name '*.a' -not -path './gen/*' -delete 2>/dev/null || true

        # Phase 2: cross-configure and build
        ./configure --prefix="${STAGING}" \
            --host=aarch64-linux-gnu --build=x86_64-linux-gnu
        # Re-touch gen/ after cross-configure (Makefile regeneration resets mtimes)
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
