#!/usr/bin/env bash
set -euo pipefail

source "/work/build/common.sh"

NAME='sugarbox'
REPO='https://github.com/Tom1975/SugarboxV2.git'
TAG="$(github_latest_tag "${REPO}")"

REPO_ROOT="${REPO_ROOT:-/work}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/artifacts}"
WORK_ROOT="${WORK_ROOT:-/work/work/emulators}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}" --submodules

while IFS= read -r target_file; do
    if ! grep -q '^#include <algorithm>' "${target_file}"; then
        log "Patching missing <algorithm> include in ${target_file}"
        sed -i '1i #include <algorithm>' "${target_file}"
    fi
done < <(grep -R "std::transform" -l "${SRC}" --include='*.cpp' --include='*.h' --include='*.hpp' 2>/dev/null || true)

mkdir -p "${BUILD}" "${STAGING}/bin"

log "Configuring"
cmake -S "${SRC}" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${STAGING}"

log "Building"
cmake --build "${BUILD}" -j"$(nproc)"

log "Installing"
cmake --install "${BUILD}" || log "Warning: cmake --install failed, falling back to manual staging"

# Explicitly stage runtime data in case cmake install rules are incomplete
for item in CART CONF Keyboards Resources ROM translations lib; do
    for src in "${STAGING}/${item}" "${BUILD}/install/${item}" "${BUILD}/${item}"; do
        if [[ -d "${src}" ]] && [[ "${src}" != "${STAGING}/${item}" ]]; then
            rsync -a "${src}/" "${STAGING}/${item}/" && log "Staged ${item}/" && break
        fi
    done
done

log "Staging binary"

candidate=""
for path in \
    "${BUILD}/Sugarbox/Sugarbox" \
    "${BUILD}/sugarbox" \
    "${BUILD}/Sugarbox" \
    "${STAGING}/Sugarbox/Sugarbox" \
    "${STAGING}/bin/Sugarbox" \
    "${STAGING}/bin/sugarbox"
do
    if [[ -x "${path}" && ! -d "${path}" ]]; then
        candidate="${path}"
        break
    fi
done

if [[ -z "${candidate}" ]]; then
    candidate="$(find "${BUILD}" "${STAGING}" \
        -type f \
        -perm /111 \
        \( -iname 'sugarbox' -o -iname 'sugarboxv2' \) \
        -print -quit 2>/dev/null || true)"
fi

[[ -n "${candidate}" ]] || die "sugarbox binary was not produced"

cp "${candidate}" "${STAGING}/bin/sugarbox"
chmod +x "${STAGING}/bin/sugarbox"
strip "${STAGING}/bin/sugarbox" || true

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
