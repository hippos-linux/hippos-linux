#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='xemu-chihiro'
REPO='https://github.com/Tovarichtch/xemu.git'
TAG="${XEMU_CHIHIRO_TAG:-$(github_latest_tag "${REPO}")}"

ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
OPTIONROM_PATCH="/work/packages/emulators/xemu/001-fix-optionrom-makefile.patch"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

if ! git -C "${SRC}" apply --reverse --check "${OPTIONROM_PATCH}" >/dev/null 2>&1; then
    git -C "${SRC}" apply --3way "${OPTIONROM_PATCH}"
fi

xemu_configure_args=()
if [[ "${CROSS_BUILD}" -eq 1 ]]; then
    xemu_configure_args+=(-a aarch64 --cross-prefix="${GNU_ARCH}-")
fi

log "Building with upstream build.sh"
cd "${SRC}"
./build.sh "${xemu_configure_args[@]+"${xemu_configure_args[@]}"}"

[[ -x "${SRC}/dist/xemu" ]] || die "xemu dist binary was not produced"

rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin" "${STAGING}/lib" "${STAGING}/data"
cp "${SRC}/dist/xemu" "${STAGING}/bin/xemu-chihiro"
cp /usr/lib/${GNU_ARCH}/libtomlplusplus.so.3* "${STAGING}/lib/" 2>/dev/null || true
patchelf --set-rpath '$ORIGIN/../lib' "${STAGING}/bin/xemu-chihiro"
cp -a "${SRC}/data/." "${STAGING}/data/"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
