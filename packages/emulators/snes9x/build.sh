#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='snes9x'
REPO='https://github.com/snes9xgit/snes9x.git'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

if ! grep -q 'openFile' "${SRC}/qt/src/main.cpp"; then
    sed -i -e '1i #include <QTimer>' \
        -e 's|^\( *\)emu.qtapp->exec();|\1if (argc > 1) QTimer::singleShot(0, [\&] { emu.window->openFile(std::string(argv[1])); });\n&|' \
        "${SRC}/qt/src/main.cpp"
fi

log "Building standalone"
rm -rf "${BUILD}"
mkdir -p "${BUILD}" "${STAGING}/bin"
cmake -S "${SRC}/qt" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}"
cmake --build "${BUILD}" -j"$(nproc)"
cmake --install "${BUILD}"
find "${BUILD}" -maxdepth 4 -name 'snes9x-qt' -type f -perm /111 -exec cp {} "${STAGING}/bin/snes9x" \; 2>/dev/null || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
