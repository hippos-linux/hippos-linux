#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='xenia-edge'
REPO='https://github.com/has207/xenia-edge'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

mkdir -p "${STAGING}/bin" "${STAGING}/lib"

cd "${SRC}"
export CC=clang-21
export CXX=clang++-21
export LDFLAGS="-fuse-ld=lld-21"

log "Running xb setup"
python3 xb setup

log "Building xenia-edge (release)"
python3 xb build --config=release

XENIA_BIN="$(find "${SRC}/build" -maxdepth 4 -name 'xenia*' -type f -perm /111 | sort | tail -1)"
[[ -n "${XENIA_BIN}" ]] || die "xenia binary not found after build"
log "Binary: ${XENIA_BIN}"
BIN_NAME="$(basename "${XENIA_BIN}")"
cp "${XENIA_BIN}" "${STAGING}/bin/${BIN_NAME}"

# Bundle clang-21 libc++ — rootfs links against system libc++ which may differ
for lib in libc++ libc++abi; do
    LIB_SRC="$(find /usr/lib/x86_64-linux-gnu -name "${lib}.so.1*" -not -type d 2>/dev/null | sort | tail -1 || true)"
    [[ -n "${LIB_SRC}" ]] && cp -L "${LIB_SRC}" "${STAGING}/lib/${lib}.so.1"
done

cat > "${STAGING}/bin/xenia-edge" <<EOF
#!/usr/bin/env bash
DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
export LD_LIBRARY_PATH="\${DIR}/../lib\${LD_LIBRARY_PATH:+:\${LD_LIBRARY_PATH}}"
exec "\${DIR}/${BIN_NAME}" "\$@"
EOF
chmod +x "${STAGING}/bin/xenia-edge"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
