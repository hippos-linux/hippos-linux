#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='openbor'
REPO='https://github.com/DCurrent/OpenBOR'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"

# Allow git commands inside Docker (source owned by host user)
git config --global --add safe.directory "${SRC}" 2>/dev/null || true

# Remove -Werror so modern gcc warnings don't abort the build
sed -i 's/ -Werror//' "${SRC}/engine/Makefile"

# Add SDL2 cflags for the LE x86_64 target (BUILD_LINUX block adds these but LE variant doesn't)
SDL2_CFLAGS="$(pkg-config --cflags sdl2 2>/dev/null || true)"
if [[ -n "${SDL2_CFLAGS}" ]]; then
    sed -i "s|CFLAGS\s*+=\s*-g -Wall|CFLAGS += ${SDL2_CFLAGS} -Wno-unused-result\\nCFLAGS += -g -Wall|" \
        "${SRC}/engine/Makefile" 2>/dev/null || true
fi

# Fix default runtime paths to match HippOS /userdata layout
sed -i \
    -e 's|= {"Paks"};|= {"/userdata/roms/openbor"};|' \
    -e 's|= {"Saves"};|= {"/userdata/saves/openbor"};|' \
    -e 's|= {"Logs"};|= {"/userdata/system/logs/openbor"};|' \
    -e 's|= {"ScreenShots"};|= {"/userdata/screenshots/openbor"};|' \
    "${SRC}/engine/sdl/sdlport.c"

sed -i \
    -e 's|fileExists("./Logs/OpenBorLog.txt")|fileExists("/userdata/system/logs/openbor/OpenBorLog.txt")|g' \
    -e 's|fileExists("./Logs/ScriptLog.txt")|fileExists("/userdata/system/logs/openbor/ScriptLog.txt")|g' \
    -e 's|fopen("./Logs/OpenBorLog.txt"|fopen("/userdata/system/logs/openbor/OpenBorLog.txt"|g' \
    -e 's|fopen("./Logs/ScriptLog.txt"|fopen("/userdata/system/logs/openbor/ScriptLog.txt"|g' \
    -e 's|strcpy(buf, "./"); strcat(buf, name); strcat(buf, "/");|strcpy(buf, "/userdata/system/configs/openbor"); strcat(buf, name); strcat(buf, "/");|' \
    -e 's|strcpy(buf, "./Paks/"); strcat(buf, name);|strcpy(buf, "/userdata/roms/openbor/"); strcat(buf, name);|' \
    "${SRC}/engine/source/utils.c"

mkdir -p "${STAGING}/bin"
cd "${SRC}/engine"
bash version.sh
make -j"$(nproc)" BUILD_LINUX_LE_x86_64=1

cp "${SRC}/engine/OpenBOR" "${STAGING}/bin/OpenBOR7530" 2>/dev/null || \
    find "${SRC}/engine" -maxdepth 2 -name 'OpenBOR' -type f -perm /111 -exec cp {} "${STAGING}/bin/OpenBOR7530" \;

ln -sf OpenBOR7530 "${STAGING}/bin/OpenBOR"
ln -sf OpenBOR7530 "${STAGING}/bin/OpenBOR4432"
ln -sf OpenBOR7530 "${STAGING}/bin/OpenBOR6412"
ln -sf OpenBOR7530 "${STAGING}/bin/OpenBOR7142"

mkdir -p "${STAGING}/lib"
cp /usr/lib/x86_64-linux-gnu/libSDL2_gfx-1.0.so.0* "${STAGING}/lib/" 2>/dev/null || true
patchelf --set-rpath '$ORIGIN/../lib' "${STAGING}/bin/OpenBOR7530" 2>/dev/null || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
