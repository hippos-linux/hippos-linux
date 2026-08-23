#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='xenia'

resolve_latest() {
    python3 - <<'PY'
import json
import sys
import urllib.request

url = "https://api.github.com/repos/xenia-project/release-builds-windows/releases?per_page=20"
req = urllib.request.Request(url, headers={"User-Agent": "hippos-build/1.0"})

try:
    with urllib.request.urlopen(req, timeout=30) as fh:
        releases = json.load(fh)
except Exception as e:
    print(f"[xenia] ERROR: request failed: {e}", file=sys.stderr)
    sys.exit(1)

for release in releases:
    version = (release.get("tag_name") or "").strip()
    assets = release.get("assets", [])

    for asset in assets:
        name = asset.get("name", "")
        download_url = asset.get("browser_download_url", "")

        if name == "xenia_master.zip" and download_url:
            print(version)
            print(download_url)
            sys.exit(0)

    for asset in assets:
        name = asset.get("name", "")
        download_url = asset.get("browser_download_url", "")

        if (
            name.lower().endswith(".zip")
            and "xenia" in name.lower()
            and "master" in name.lower()
            and download_url
        ):
            print(version)
            print(download_url)
            sys.exit(0)

print("[xenia] ERROR: no xenia master zip found in recent releases", file=sys.stderr)
sys.exit(1)
PY
}

if [[ -n "${XENIA_VERSION:-}" && -n "${XENIA_DOWNLOAD_URL:-}" ]]; then
    VERSION="${XENIA_VERSION}"
    DOWNLOAD_URL="${XENIA_DOWNLOAD_URL}"
else
    mapfile -t XENIA_INFO < <(resolve_latest)
    VERSION="${XENIA_VERSION:-${XENIA_INFO[0]:-}}"
    DOWNLOAD_URL="${XENIA_DOWNLOAD_URL:-${XENIA_INFO[1]:-}}"
fi

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

mkdir -p "${BUILD}" "${STAGING}/bin" "${STAGING}/emulator"

ARCHIVE="${BUILD}/xenia_master.zip"

if [[ -f "${ARCHIVE}" ]] && ! unzip -tq "${ARCHIVE}" >/dev/null 2>&1; then
    log "Discarding invalid cached archive"
    rm -f "${ARCHIVE}"
fi

if [[ ! -f "${ARCHIVE}" ]]; then
    [[ -n "${VERSION}" ]] || die "Could not resolve latest Xenia version"
    [[ -n "${DOWNLOAD_URL}" ]] || die "Could not resolve Xenia download URL"

    log "Downloading Xenia ${VERSION}"
    curl -fL "${DOWNLOAD_URL}" -o "${ARCHIVE}"
fi

rm -rf "${STAGING}/emulator"
mkdir -p "${STAGING}/emulator"

unzip -o "${ARCHIVE}" -d "${STAGING}/emulator" -x '*.pdb' >/dev/null

if ! find "${STAGING}/emulator" -type f -iname 'xenia*.exe' | grep -q .; then
    die "Xenia archive extracted but no xenia exe was found"
fi

touch "${STAGING}/emulator/portable.txt"

cat > "${STAGING}/bin/xenia" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail

XENIA_HOME="${XENIA_HOME:-/userdata/system/emulators/xenia/current}"
XENIA_PREFIX="${XENIA_PREFIX:-/userdata/wine-bottles/xenia/current}"
XENIA_EXE="${XENIA_EXE:-${XENIA_HOME}/xenia.exe}"

mkdir -p "${XENIA_HOME}" "${XENIA_PREFIX}"
touch "${XENIA_HOME}/portable.txt"

export WINEPREFIX="${XENIA_PREFIX}"
export WINEARCH=win64
export WINEDEBUG=-all

exec /opt/wine-builds/wine-proton/bin/wine "${XENIA_EXE}" "$@"
LAUNCHER

chmod +x "${STAGING}/bin/xenia"

write_artifact_version "${STAGING}" "${VERSION}"
log "Done. Artifact at ${STAGING}"
