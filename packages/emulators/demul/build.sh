#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='demul'

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

mkdir -p "${STAGING}/bin"

# Demul is Windows-only and has no public release API.
# The user must manually place demul.exe in ~/.local/share/demul/
cat > "${STAGING}/bin/demul" <<'LAUNCHER'
#!/usr/bin/env bash
DEMUL_EXE="${HOME}/.local/share/demul/demul.exe"

if [[ ! -f "${DEMUL_EXE}" ]]; then
    echo "Demul not found."
    echo "Download Demul from http://demul.emulation64.com and extract to:"
    echo "  ${HOME}/.local/share/demul/"
    exit 1
fi

export WINEPREFIX=/userdata/wine-bottles/demul
export WINEARCH=win64
export WINEDEBUG=-all
exec /opt/wine-builds/wine-proton/bin/wine "${DEMUL_EXE}" "$@"
LAUNCHER
chmod +x "${STAGING}/bin/demul"

write_artifact_version "${STAGING}" "launcher"
log "Done. Artifact at ${STAGING}"
