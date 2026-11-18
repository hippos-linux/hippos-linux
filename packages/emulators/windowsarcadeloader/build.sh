#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"
source "${REPO_ROOT}/build/common.sh"

NAME='windowsarcadeloader'
REPO='https://github.com/aderumier/windowsarcadeloader.git'
TAG="${WINDOWSARCADELOADER_TAG:-$(github_latest_tag "${REPO}")}"

WORK_ROOT="${WORK_ROOT:-${REPO_ROOT}/work/emulators}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-${REPO_ROOT}/artifacts}"
SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"
IMAGE_NAME="hippos-${NAME}-builder"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${TAG}" "${SRC}"
sudo chown -R "$(id -u):$(id -g)" "${WORK_ROOT}/${NAME}" "${STAGING}" 2>/dev/null || true
mkdir -p "${BUILD}" "${STAGING}"

log "Building Docker image (Ubuntu 24.04, Rust + MinGW + Mono + SDL3 deps)"
cat > "${BUILD}/Dockerfile" <<'EOF'
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl git \
        gcc-mingw-w64 mono-mcs mono-devel cmake pkg-config \
        libx11-dev libxext-dev libxrandr-dev libxcursor-dev libxfixes-dev libxi-dev \
        libxss-dev libxtst-dev libxkbcommon-dev libdrm-dev libgbm-dev \
        libgl-dev libegl-dev libgles-dev libdbus-1-dev libibus-1.0-dev \
        libudev-dev libwayland-dev wayland-protocols libdecor-0-dev \
        libasound2-dev libpulse-dev libpipewire-0.3-dev libjack-jackd2-dev \
        libsndio-dev libusb-1.0-0-dev liburing-dev \
    && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --profile minimal --default-toolchain stable \
    && /root/.cargo/bin/rustup target add i686-pc-windows-gnu x86_64-pc-windows-gnu
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /windowsarcadeloader
COPY . .
RUN LAUNCHER_FEATURES=sdl3/build-from-source ./build.sh
RUN tools/batocera/install.sh /output
EOF

docker build --no-cache -t "${IMAGE_NAME}" -f "${BUILD}/Dockerfile" "${SRC}"

cid="$(docker create "${IMAGE_NAME}")"
trap 'docker rm -f "${cid}" >/dev/null 2>&1 || true' EXIT
rm -rf "${BUILD}/output"; mkdir -p "${BUILD}/output"
docker cp "${cid}:/output/." "${BUILD}/output/"
docker rm -f "${cid}" >/dev/null 2>&1 || true
trap - EXIT

cp -a "${BUILD}/output/." "${STAGING}/"
[[ -x "${STAGING}/arcade-launcher" ]] || die "arcade-launcher binary was not produced"

write_artifact_version "${STAGING}" "${TAG}"
log "Done. Artifact at ${STAGING}"
