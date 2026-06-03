#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='model2emu'
DOWNLOAD_URL='https://github.com/batocera-linux/model2emu/raw/main/m2emulator.zip'

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

mkdir -p "${BUILD}" "${STAGING}/bin" "${STAGING}/emulator"

ARCHIVE="${BUILD}/m2emulator.zip"

if [[ ! -f "${ARCHIVE}" ]]; then
    log "Downloading Model2Emu payload"
    curl -L "${DOWNLOAD_URL}" -o "${ARCHIVE}"
fi

unzip -o "${ARCHIVE}" -d "${STAGING}/emulator"

# Launcher — invokes the Windows binary via Wine
cat > "${STAGING}/bin/model2emu" <<'LAUNCHER'
#!/usr/bin/env bash
export WINEPREFIX=/userdata/wine-bottles/model2emu
export WINEARCH=win64
exec /opt/wine-builds/wine-tkg/bin/wine \
    /opt/emulators/model2emu/emulator/emulator_multicpu.exe "$@"
LAUNCHER
chmod +x "${STAGING}/bin/model2emu"

write_artifact_version "${STAGING}" "$(date +%Y%m%d)"
log "Done. Artifact at ${STAGING}"
