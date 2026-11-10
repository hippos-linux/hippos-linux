#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"
source "${REPO_ROOT}/build/common.sh"

NAME='linuxloader'
REPO='https://github.com/lindbergh-loader/linuxloader.git'
REF="${LINUXLOADER_REF:-v3.0.12}"

WORK_ROOT="${WORK_ROOT:-${REPO_ROOT}/work/emulators}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-${REPO_ROOT}/artifacts}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
IMAGE_NAME="hippos-${NAME}-builder"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${REF}" "${SRC}" --submodules
sudo chown -R "$(id -u):$(id -g)" "${WORK_ROOT}/${NAME}" "${STAGING}" 2>/dev/null || true
mkdir -p "${BUILD}" "${STAGING}/bin"

log "Writing Ubuntu 22.04 builder (upstream's recommended 32-bit toolchain)"
cat > "${BUILD}/Dockerfile" <<'EOF'
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git sudo make cmake build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /linuxloader
COPY . .
RUN bash scripts/appimage/install-packages.sh
RUN bash scripts/appimage/build-deps.sh
RUN make
RUN mkdir -p /output && cp -a build-linux /output/
EOF

docker build --no-cache -t "${IMAGE_NAME}" -f "${BUILD}/Dockerfile" "${SRC}"

cid="$(docker create "${IMAGE_NAME}")"
trap 'docker rm -f "${cid}" >/dev/null 2>&1 || true' EXIT
rm -rf "${BUILD}/output"; mkdir -p "${BUILD}/output"
docker cp "${cid}:/output/build-linux" "${BUILD}/output/build-linux"
docker rm -f "${cid}" >/dev/null 2>&1 || true
trap - EXIT

# Stage the whole build-linux payload (loader + Sega shims + bundled ll-deps libs)
cp -a "${BUILD}/output/build-linux/." "${STAGING}/"
found="$(find "${STAGING}" -maxdepth 3 -name 'linuxloader' -type f -perm /111 -print -quit 2>/dev/null || true)"
[[ -n "${found}" ]] || die "linuxloader binary was not produced"
[[ -x "${STAGING}/bin/linuxloader" ]] || cp "${found}" "${STAGING}/bin/linuxloader"

write_artifact_version "${STAGING}" "${REF}"
log "Done. Artifact at ${STAGING}"
