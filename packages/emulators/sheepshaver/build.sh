#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='sheepshaver'
REPO='https://github.com/kanjitalk755/macemu.git'
REF="${SHEEPSHAVER_REF:-master}"
SHA="${SHEEPSHAVER_SHA:-0407cbd519b6e153431ba1cca84a41407869ec31}"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
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

cd "${SRC}/SheepShaver"
make links
cd src/Unix
NO_CONFIGURE=1 ./autogen.sh
./configure --enable-sdl-video --enable-sdl-audio --disable-vosf --without-mon --with-gtk=no
make -j"$(nproc)"

rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin"
install -m755 SheepShaver "${STAGING}/bin/sheepshaver"
"${STRIP:-strip}" "${STAGING}/bin/sheepshaver"

write_artifact_version "${STAGING}" "${SHA:0:12}"
log "Done. Artifact at ${STAGING}"
