#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/../../.." && pwd)}"

source "${REPO_ROOT}/build/common.sh"

NAME='lindbergh-loader'
REPO='https://github.com/lindbergh-loader/lindbergh-loader.git'
REF="${LINDBERGH_LOADER_REF:-v2.1.4}"

WORK_ROOT="${WORK_ROOT:-${REPO_ROOT}/work/emulators}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-${REPO_ROOT}/artifacts}"

SRC="${WORK_ROOT}/${NAME}/source"
BUILD="${WORK_ROOT}/${NAME}/build"
STAGING="${ARTIFACT_ROOT}/emulators/${NAME}"

IMAGE_NAME="hippos-${NAME}-builder"

log() { printf '[build:%s] %s\n' "${NAME}" "$*"; }

clone_source "${REPO}" "${REF}" "${SRC}"

# Fix ownership if the work dir or artifact dir was previously created by Docker (root-owned)
sudo chown -R "$(id -u):$(id -g)" "${WORK_ROOT}/${NAME}" "${STAGING}" 2>/dev/null || true

mkdir -p "${BUILD}" "${STAGING}/bin"

log "Writing patched Dockerfile"

cat > "${BUILD}/Dockerfile" <<'EOF'
FROM ubuntu:22.04 AS lindbergh-build

ENV DEBIAN_FRONTEND=noninteractive

RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        gcc-multilib \
        g++-multilib \
        cmake \
        fuse \
        freeglut3-dev:i386 \
        libvdpau1:i386 \
        libstdc++5:i386 \
        libxmu6:i386 \
        libpcsclite1:i386 \
        libncurses5:i386 \
        unzip \
        libsndio-dev \
        libsndio-dev:i386 \
        pulseaudio-utils:i386 \
        libasound2 \
        libasound2-dev \
        libasound2:i386 \
        libasound2-dev:i386 \
        libdbus-1-dev \
        libdbus-1-dev:i386 \
        libpulse-dev \
        libudev-dev:i386 \
        zlib1g:i386 \
        libgpg-error0:i386 \
        libxcursor-dev:i386 \
        libxfixes-dev:i386 \
        libxi-dev:i386 \
        libxrandr-dev:i386 \
        libxss-dev:i386 \
        libxxf86vm-dev:i386 \
        libfreetype6-dev:i386 \
        git \
        make \
        pkg-config \
        ninja-build \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /lindbergh-loader

COPY . .

RUN if [ -f libs/libs.tar ]; then \
        tar -xf libs/libs.tar -C /usr/lib/i386-linux-gnu; \
    else \
        cp -a libs/*.so* /usr/lib/i386-linux-gnu/; \
    fi

RUN if [ -f libs/includes.tar ]; then \
        tar -xf libs/includes.tar -C /usr/include; \
    else \
        true; \
    fi

RUN git clone --depth=1 --branch release-3.4.8 https://github.com/libsdl-org/SDL.git /tmp/SDL && \
    cmake -S /tmp/SDL -B /tmp/SDL/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr \
        -DCMAKE_C_FLAGS=-m32 \
        -DCMAKE_CXX_FLAGS=-m32 \
        -DSDL_SHARED=ON \
        -DSDL_STATIC=OFF \
        -DSDL_X11_XTEST=OFF && \
    cmake --build /tmp/SDL/build -j"$(nproc)" && \
    cmake --install /tmp/SDL/build

RUN git clone --depth=1 https://github.com/libsdl-org/SDL_image.git /tmp/SDL_image && \
    cmake -S /tmp/SDL_image -B /tmp/SDL_image/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr \
        -DCMAKE_C_FLAGS=-m32 \
        -DCMAKE_CXX_FLAGS=-m32 \
        -DSDL3IMAGE_SAMPLES=OFF \
        -DSDL3IMAGE_TESTS=OFF && \
    cmake --build /tmp/SDL_image/build -j"$(nproc)" && \
    cmake --install /tmp/SDL_image/build

RUN git clone --depth=1 https://github.com/libsdl-org/SDL_ttf.git /tmp/SDL_ttf && \
    cmake -S /tmp/SDL_ttf -B /tmp/SDL_ttf/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr \
        -DCMAKE_C_FLAGS=-m32 \
        -DCMAKE_CXX_FLAGS=-m32 \
        -DSDLTTF_SAMPLES=OFF && \
    cmake --build /tmp/SDL_ttf/build -j"$(nproc)" && \
    cmake --install /tmp/SDL_ttf/build

# FAudio: built from source as static 32-bit lib (same as upstream build-deps.sh)
RUN git clone --depth=1 https://github.com/FNA-XNA/FAudio.git /tmp/FAudio && \
    cmake -S /tmp/FAudio -B /tmp/FAudio/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr \
        -DCMAKE_C_FLAGS=-m32 \
        -DBUILD_SHARED_LIBS=OFF && \
    cmake --build /tmp/FAudio/build -j"$(nproc)" && \
    cmake --install /tmp/FAudio/build

RUN make && mkdir -p /output && cp -r ./build /output
EOF

log "Building dedicated patched Docker image"

docker build --no-cache \
    -t "${IMAGE_NAME}" \
    -f "${BUILD}/Dockerfile" \
    "${SRC}"

log "Extracting build output"

container_id="$(docker create "${IMAGE_NAME}")"

cleanup_container() {
    docker rm -f "${container_id}" >/dev/null 2>&1 || true
}
trap cleanup_container EXIT

rm -rf "${BUILD}/output"
mkdir -p "${BUILD}/output" "${STAGING}/bin"

docker cp "${container_id}:/output/build" "${BUILD}/output/build"

cleanup_container
trap - EXIT

found_bin="$(find "${BUILD}/output/build" \
    -maxdepth 4 \
    -type f \
    -perm /111 \
    \( -iname 'lindbergh-loader*' -o -iname 'lindbergh*' \) \
    -print -quit 2>/dev/null || true)"

[[ -n "${found_bin}" ]] || die "lindbergh-loader binary was not produced"

cp "${found_bin}" "${STAGING}/bin/lindbergh-loader"
chmod +x "${STAGING}/bin/lindbergh-loader"

log "Staging inject libraries"
mkdir -p "${STAGING}/lib"
find "${BUILD}/output/build" -maxdepth 4 \
    \( -name "*.so" -o -name "*.so.*" \) -type f \
    -exec cp {} "${STAGING}/lib/" \;

write_artifact_version "${STAGING}" "${REF}"
log "Done. Artifact at ${STAGING}"
