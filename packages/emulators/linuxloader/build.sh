#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"
source "${REPO_ROOT}/build/common.sh"

NAME='linuxloader'
REPO='https://github.com/aderumier/linuxloader.git'
REF="${LINUXLOADER_REF:-rawthrills}"
SHA="${LINUXLOADER_SHA:-f8fcf37572bd5fd375572c23e53bc9b82d7846c1}"

WORK_ROOT="${WORK_ROOT:-${REPO_ROOT}/work/emulators}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-${REPO_ROOT}/artifacts}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
IMAGE_NAME="hippos-${NAME}-builder"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

if [[ -d "${SRC}/.git" && "$(git -C "${SRC}" rev-parse HEAD 2>/dev/null)" != "${SHA}" ]]; then
    rm -rf "${SRC}"
fi
if [[ ! -d "${SRC}/.git" ]]; then
    log "Cloning ${REPO} at ${SHA:0:12}"
    git clone --depth=1 --branch "${REF}" "${REPO}" "${SRC}"
    if [[ "$(git -C "${SRC}" rev-parse HEAD)" != "${SHA}" ]]; then
        git -C "${SRC}" fetch --depth=1 origin "${SHA}"
        git -C "${SRC}" checkout --quiet "${SHA}"
    fi
    git -C "${SRC}" submodule update --init --recursive
fi
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
RUN make linux
RUN mkdir -p /output && cp -a build-linux /output/
EOF

docker build --no-cache -t "${IMAGE_NAME}" -f "${BUILD}/Dockerfile" "${SRC}"

cid="$(docker create "${IMAGE_NAME}")"
trap 'docker rm -f "${cid}" >/dev/null 2>&1 || true' EXIT
rm -rf "${BUILD}/output"; mkdir -p "${BUILD}/output"
docker cp "${cid}:/output/build-linux" "${BUILD}/output/build-linux"
docker rm -f "${cid}" >/dev/null 2>&1 || true
trap - EXIT

found="$(find "${BUILD}/output/build-linux" -maxdepth 3 -name 'linuxloader' -type f -perm /111 -print -quit 2>/dev/null || true)"
[[ -n "${found}" ]] || die "linuxloader binary was not produced"
rm -rf "${STAGING}"
mkdir -p "${STAGING}/bin"
cp -a "${BUILD}/output/build-linux/." "${STAGING}/"
install -m755 "${found}" "${STAGING}/bin/linuxloader"

write_artifact_version "${STAGING}" "${SHA:0:12}"
log "Done. Artifact at ${STAGING}"
