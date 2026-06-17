ARG QT_VERSION=6.11.1

# ── Stage 1: amd64 Qt 6.11 ───────────────────────────────────────────────────
FROM debian:trixie AS amd64-qt

ARG QT_VERSION

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        perl \
        python3 \
        ca-certificates \
        curl \
        xz-utils \
        pkg-config \
        libgl-dev \
        libegl-dev \
        libgles-dev \
        libdrm-dev \
        libgbm-dev \
        libfontconfig1-dev \
        libfreetype-dev \
        libdbus-1-dev \
        libssl-dev \
        zlib1g-dev \
        libx11-dev \
        libx11-xcb-dev \
        libxcb1-dev \
        libxcb-cursor-dev \
        libxcb-glx0-dev \
        libxcb-icccm4-dev \
        libxcb-image0-dev \
        libxcb-keysyms1-dev \
        libxcb-randr0-dev \
        libxcb-render-util0-dev \
        libxcb-shape0-dev \
        libxcb-sync-dev \
        libxcb-util-dev \
        libxcb-xfixes0-dev \
        libxcb-xkb-dev \
        libxkbcommon-dev \
        libxkbcommon-x11-dev \
        libxext-dev \
        libxfixes-dev \
        libxi-dev \
        libxrandr-dev \
        libxrender-dev \
        libxss-dev \
        libxtst-dev \
        libxcb-render0-dev \
        libxcb-shm0-dev \
        libxcb-xinerama0-dev \
        libxcb-xinput-dev \
        libxcb-xtest0-dev \
        libxcb-damage0-dev \
        libva-dev \
        libvdpau-dev \
        libwayland-dev \
        libwayland-egl-backend-dev \
        wayland-protocols \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libswresample-dev \
        libswscale-dev \
        libpulse-dev \
        libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN curl -fsSL \
    "https://download.qt.io/official_releases/qt/${QT_VERSION%.*}/${QT_VERSION}/single/qt-everywhere-src-${QT_VERSION}.tar.xz" \
    -o qt-src.tar.xz

RUN mkdir src && tar -xJf qt-src.tar.xz -C src --strip-components=1 && rm qt-src.tar.xz

RUN mkdir qt-build && cd qt-build && \
    ../src/configure \
        -prefix /opt/hippos/qt/6.11 \
        -release \
        -shared \
        -opensource \
        -confirm-license \
        -nomake examples \
        -nomake tests \
        -submodules qtbase,qttools,qtsvg,qtmultimedia,qtwayland,qtdeclarative \
        -- -G Ninja && \
    cmake --build . -j"$(nproc)" && \
    cmake --install .

RUN tar -cJf /qt-6.11-hippos-x86_64.tar.xz -C /opt/hippos/qt 6.11

CMD ["/bin/bash"]

# ── Stage 2: arm64 Qt 6.11 (cross-compiled from amd64) ───────────────────────
# Uses the arm64 emulator bulk image as base — all cross-compile tools and arm64
# sysroot packages are already present; no apt installs needed here.
FROM hippos-emulator-bulk-arm64:latest AS arm64-qt

ARG QT_VERSION

# Extract the pre-built amd64 Qt as host tools (moc/rcc/uic/qmake).
# artifacts/qt/ is excluded from .dockerignore except for this file.
COPY artifacts/qt/qt-6.11-hippos-x86_64.tar.xz /tmp/qt-host.tar.xz
RUN mkdir -p /opt/hippos/qt && \
    tar -xJf /tmp/qt-host.tar.xz -C /opt/hippos/qt && \
    mv /opt/hippos/qt/6.11 /opt/hippos/qt/6.11-host && \
    rm /tmp/qt-host.tar.xz

COPY docker/qt/aarch64-qt-toolchain.cmake /opt/aarch64-qt-toolchain.cmake

WORKDIR /build

RUN curl -fsSL \
    "https://download.qt.io/official_releases/qt/${QT_VERSION%.*}/${QT_VERSION}/single/qt-everywhere-src-${QT_VERSION}.tar.xz" \
    -o qt-src.tar.xz

RUN mkdir src && tar -xJf qt-src.tar.xz -C src --strip-components=1 && rm qt-src.tar.xz

# Cross-compile Qt for arm64.
# No qttools: host tools (moc/rcc/uic/qmake) come from 6.11-host; arm64 binaries
# of designer/linguist/qdoc are not needed for building emulators.
RUN mkdir qt-build && cd qt-build && \
    ../src/configure \
        -prefix /opt/hippos/qt/6.11 \
        -release \
        -shared \
        -opensource \
        -confirm-license \
        -nomake examples \
        -nomake tests \
        -qt-host-path /opt/hippos/qt/6.11-host \
        -submodules qtbase,qtsvg,qtmultimedia,qtwayland,qtdeclarative \
        -- \
        -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE=/opt/aarch64-qt-toolchain.cmake \
        -DQT_HOST_PATH=/opt/hippos/qt/6.11-host \
        -DQT_HOST_PATH_CMAKE_DIR=/opt/hippos/qt/6.11-host/lib/cmake && \
    cmake --build . -j"$(nproc)" && \
    cmake --install .

RUN tar -cJf /qt-6.11-hippos-aarch64.tar.xz -C /opt/hippos/qt 6.11

CMD ["/bin/bash"]
