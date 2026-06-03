#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='ryujinx'
REPO='https://git.ryujinx.app/projects/Ryubing.git'
VERSION="$(forgejo_latest_tag "${REPO}")"
DOWNLOAD_URL="https://git.ryujinx.app/projects/Ryubing/releases/download/${VERSION}/ryujinx-${VERSION}-linux_x64.tar.gz"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

mkdir -p "${BUILD}" "${STAGING}/bin"

log "Installing Ryujinx ${VERSION}"

TARBALL="${BUILD}/ryujinx-${VERSION}-linux_x64.tar.gz"

if [[ -f "${TARBALL}" ]] && ! gzip -t "${TARBALL}" >/dev/null 2>&1; then
    log "Discarding invalid cached archive"
    rm -f "${TARBALL}"
fi

if [[ ! -f "${TARBALL}" ]]; then
    log "Downloading Ryujinx ${VERSION}"
    curl -fL "${DOWNLOAD_URL}" -o "${TARBALL}"
fi

rm -rf "${BUILD}/extract"
mkdir -p "${BUILD}/extract"

tar -xzf "${TARBALL}" -C "${BUILD}/extract"

find "${BUILD}/extract" -maxdepth 4 -type f -perm /111 -print

RYUJINX_BIN="$(find "${BUILD}/extract" -maxdepth 4 -type f -perm /111 \( -iname 'Ryujinx' -o -iname 'Ryujinx.sh' -o -iname 'ryujinx' \) | head -1)"

[[ -n "${RYUJINX_BIN}" ]] || die "Ryujinx executable not found after extraction"

cp -a "$(dirname "${RYUJINX_BIN}")/." "${STAGING}/bin/"

# libavcodec.so.* is bundled alongside libavutil.so.* in bin/, but its embedded
# RUNPATH points to /opt/hippos/qt/6.11/lib rather than $ORIGIN, so the dynamic
# linker cannot find the sibling libavutil at runtime. Fix the RUNPATH in-place.
find "${STAGING}/bin" -name "libavcodec.so.*" -type f | while read -r f; do
    patchelf --set-rpath '$ORIGIN' "${f}" 2>/dev/null || true
done

write_artifact_version "${STAGING}" "${VERSION}"
log "Done. Artifact at ${STAGING}"
