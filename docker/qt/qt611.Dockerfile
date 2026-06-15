FROM debian:trixie AS builder

ARG QT_VERSION=6.11.1

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

ARG TARGETARCH=amd64

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

RUN NATIVE_ARCH=$([ "${TARGETARCH}" = "amd64" ] && echo "x86_64" || echo "aarch64") && \
    tar -cJf "/qt-6.11-hippos-${NATIVE_ARCH}.tar.xz" -C /opt/hippos/qt 6.11

CMD ["/bin/bash"]
