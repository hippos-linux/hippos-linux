#!/usr/bin/env bash
# setup.sh — prepare a fresh checkout to build HippOS images.
#
# Downloads the build kit (image build scripts, kernels, kernel tools, Qt,
# frontend) and the released emulators, so ./build.sh can produce an image
# without compiling anything. Run it again after a release to update.
#
# Usage:
#   ./setup.sh [--arch amd64|arm64]
#
# Needs a HippOS dev token: put it in dev-token.txt in the repo root, or set
# HIPPOS_DEV_TOKEN.
#
# An emulator you built yourself (artifacts/<arch>/emulators/<name>) is never
# replaced. Delete its folder to go back to the released build.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API="https://hippos-linux.org/api/update"
ARCH="amd64"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch) ARCH="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 1 ;;
    esac
done
[[ "${ARCH}" == amd64 || "${ARCH}" == arm64 ]] || { echo "--arch must be amd64 or arm64" >&2; exit 1; }

TOKEN="${HIPPOS_DEV_TOKEN:-}"
[[ -n "${TOKEN}" || ! -f "${REPO_ROOT}/dev-token.txt" ]] || TOKEN="$(tr -d '[:space:]' < "${REPO_ROOT}/dev-token.txt")"
[[ -n "${TOKEN}" ]] || { echo "No dev token: add dev-token.txt or set HIPPOS_DEV_TOKEN" >&2; exit 1; }

for tool in curl tar zstd sha256sum python3; do
    command -v "${tool}" >/dev/null 2>&1 || { echo "required tool not found: ${tool}" >&2; exit 1; }
done

fetch() {
    curl -fL --progress-bar --retry 3 -H "Authorization: Bearer ${TOKEN}" -o "$2" "$1"
}

DOWNLOAD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hippos-setup.XXXXXX")"
trap 'rm -rf "${DOWNLOAD_DIR}"' EXIT

KIT="hippos-build-kit-${ARCH}.tar.zst"
echo "[setup] Downloading ${KIT}"
fetch "${API}/build-kit/${KIT}" "${DOWNLOAD_DIR}/${KIT}"
fetch "${API}/build-kit/${KIT}.sha256" "${DOWNLOAD_DIR}/${KIT}.sha256"
(cd "${DOWNLOAD_DIR}" && sha256sum -c --quiet "${KIT}.sha256")
echo "[setup] Extracting build kit"
tar -C "${REPO_ROOT}" --zstd -xf "${DOWNLOAD_DIR}/${KIT}"
rm -f "${DOWNLOAD_DIR}/${KIT}"

MANIFEST="${DOWNLOAD_DIR}/manifest.json"
if ! curl -fsL -o "${MANIFEST}" "${API}/manifest-${ARCH}.json"; then
    echo "[setup] No published ${ARCH} release yet: build emulators with build/build-emulator.sh"
    exit 0
fi

python3 -I - "${MANIFEST}" "${REPO_ROOT}" "${ARCH}" > "${DOWNLOAD_DIR}/emulators.tsv" <<'PYEOF'
import json, os, sys

manifest_path, repo_root, arch = sys.argv[1:4]
payloads = json.load(open(manifest_path))["payloads"]
os_version = open(os.path.join(repo_root, "overlays/rootfs/usr/share/hippos/version")).read().strip()

def version_key(version):
    return tuple(int(part) for part in version.split("."))

emulators = payloads.get("emulators", {})
builds = payloads.get("emulator_builds", {})
for name in sorted(set(emulators) | set(builds)):
    usable = [b for b in builds.get(name, []) if version_key(b["min_os"]) <= version_key(os_version)]
    entry = max(usable, key=lambda b: version_key(b["min_os"])) if usable else emulators.get(name)
    if entry:
        print(name, entry["url"], entry["sha256"], sep="\t")
PYEOF

EMULATORS_DIR="${REPO_ROOT}/artifacts/${ARCH}/emulators"
FETCHED_DIR="${REPO_ROOT}/artifacts/${ARCH}/.setup-emulators"
mkdir -p "${EMULATORS_DIR}" "${FETCHED_DIR}"

while IFS=$'\t' read -r name url sha256; do
    target="${EMULATORS_DIR}/${name}"
    record="${FETCHED_DIR}/${name}.sha256"
    if [[ -d "${target}" && ! -f "${record}" ]]; then
        echo "[setup] ${name}: local build, keeping it"
        continue
    fi
    if [[ -f "${record}" && "$(cat "${record}")" == "${sha256}" ]]; then
        continue
    fi
    echo "[setup] ${name}: downloading"
    tarball="${DOWNLOAD_DIR}/${name}.tar.zst"
    fetch "${url}" "${tarball}"
    echo "${sha256}  ${tarball}" | sha256sum -c --quiet
    rm -rf "${target}"
    mkdir -p "${target}"
    tar -C "${target}" --zstd -xf "${tarball}"
    rm -f "${tarball}"
    echo "${sha256}" > "${record}"
done < "${DOWNLOAD_DIR}/emulators.tsv"

echo "[setup] Done. Run ./build.sh --arch ${ARCH} to build the image."
