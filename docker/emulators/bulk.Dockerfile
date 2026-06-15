FROM hippos-emulator-base:latest

ARG TARGETARCH=amd64

ENV DEBIAN_FRONTEND=noninteractive
ENV DEBCONF_NONINTERACTIVE_SEEN=true

# ── Step 1: enable arm64 multiarch when cross-compiling ──────────────────────
RUN if [ "${TARGETARCH}" = "arm64" ]; then dpkg --add-architecture arm64; fi

# ── Step 2: host-only build tools (always amd64, no arch suffix) ─────────────
# Includes header-only dev packages (Architecture:all) that live in /usr/include
# and are visible to cross-compilers without an :arm64 suffix.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        autoconf \
        autoconf-archive \
        automake \
        autopoint \
        bison \
        cargo \
        clang \
        cmake \
        curl \
        dbus \
        default-jdk-headless \
        dos2unix \
        xa65 \
        extra-cmake-modules \
        ffmpeg \
        flex \
        fonts-dejavu-core \
        g++ \
        gcc \
        gettext \
        git \
        glslang-tools \
        golang-go \
        libtool \
        libcereal-dev \
        libcxxopts-dev \
        libglm-dev \
        libhowardhinnant-date-dev \
        libstb-dev \
        libtomlplusplus-dev \
        lld \
        llvm \
        llvm-19 \
        llvm-19-dev \
        make \
        mesa-utils \
        nasm \
        ninja-build \
        nlohmann-json3-dev \
        p7zip-full \
        patchelf \
        pkg-config \
        pkgconf \
        python3 \
        python3-pip \
        python3-tomli \
        python3-yaml \
        python3.13-venv \
        qt6-base-dev \
        qt6-tools-dev-tools \
        rapidjson-dev \
        re2c \
        rsync \
        rustc \
        spirv-headers \
        spirv-tools \
        tar \
        udev \
        unzip \
        vim-common \
        wayland-protocols \
        wget \
        xorg \
        xserver-xorg-core \
        xwayland \
        xxd \
        xz-utils \
        zip \
        zstd \
        file \
    && rm -rf /var/lib/apt/lists/*

# ── Step 3: cross-compiler for arm64 (only when TARGETARCH=arm64) ─────────────
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends \
            gcc-aarch64-linux-gnu \
            g++-aarch64-linux-gnu \
            binutils-aarch64-linux-gnu \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# ── Step 4: target libraries ──────────────────────────────────────────────────
# For amd64: native packages.  For arm64: :arm64 packages via multiarch.
# _sfx is set before the package list and expanded by the shell before apt sees it.
RUN set -e; \
    _sfx=""; \
    if [ "${TARGETARCH}" = "arm64" ]; then _sfx=":arm64"; apt-get update; fi; \
    apt-get install -y --no-install-recommends \
        freeglut3-dev${_sfx} \
        glslang-dev${_sfx} \
        libaio-dev${_sfx} \
        libao-dev${_sfx} \
        libarchive-dev${_sfx} \
        libasound2-dev${_sfx} \
        libavcodec-dev${_sfx} \
        libavfilter-dev${_sfx} \
        libavformat-dev${_sfx} \
        libavif-dev${_sfx} \
        libavutil-dev${_sfx} \
        libbacktrace-dev${_sfx} \
        libbluetooth-dev${_sfx} \
        libboost-all-dev${_sfx} \
        libbz2-dev${_sfx} \
        libcap-dev${_sfx} \
        libcubeb-dev${_sfx} \
        libcurl4-openssl-dev${_sfx} \
        libdbus-1-dev${_sfx} \
        libdecor-0-dev${_sfx} \
        libdisplay-info-dev${_sfx} \
        libdrm-dev${_sfx} \
        libegl-dev${_sfx} \
        libeis-dev${_sfx} \
        libenet-dev${_sfx} \
        libepoxy-dev${_sfx} \
        libevdev-dev${_sfx} \
        libexpat1-dev${_sfx} \
        libfaad-dev${_sfx} \
        libfaudio-dev${_sfx} \
        libflac-dev${_sfx} \
        libfmt-dev${_sfx} \
        libfontconfig-dev${_sfx} \
        libfreetype-dev${_sfx} \
        libgbm-dev${_sfx} \
        libgl-dev${_sfx} \
        libgl1-mesa-dev${_sfx} \
        libgles2-mesa-dev${_sfx} \
        libglew-dev${_sfx} \
        libglu1-mesa-dev${_sfx} \
        libglvnd-dev${_sfx} \
        libgtk-3-dev${_sfx} \
        libgudev-1.0-dev${_sfx} \
        libharfbuzz-dev${_sfx} \
        libhidapi-dev${_sfx} \
        libibus-1.0-dev${_sfx} \
        libinih-dev${_sfx} \
        libinput-dev${_sfx} \
        libjack-dev${_sfx} \
        libjpeg-dev${_sfx} \
        liblcms2-dev${_sfx} \
        libluajit-5.1-dev${_sfx} \
        liblz4-dev${_sfx} \
        libminizip-dev${_sfx} \
        libmodplug-dev${_sfx} \
        libmpeg2-4-dev${_sfx} \
        libmpg123-dev${_sfx} \
        libncurses-dev${_sfx} \
        libogg-dev${_sfx} \
        libopenal-dev${_sfx} \
        libopengl-dev${_sfx} \
        libopus-dev${_sfx} \
        libopusfile-dev${_sfx} \
        libpcap-dev${_sfx} \
        libphysfs-dev${_sfx} \
        libpipewire-0.3-dev${_sfx} \
        libpixman-1-dev${_sfx} \
        libpng-dev${_sfx} \
        libportmidi-dev${_sfx} \
        libpugixml-dev${_sfx} \
        libpulse-dev${_sfx} \
        libreadline-dev${_sfx} \
        librtmidi-dev${_sfx} \
        libsamplerate0-dev${_sfx} \
        libsdl2-dev${_sfx} \
        libsdl2-gfx-dev${_sfx} \
        libsdl2-image-dev${_sfx} \
        libsdl2-mixer-dev${_sfx} \
        libsdl2-net-dev${_sfx} \
        libsdl2-ttf-dev${_sfx} \
        libsdl3-dev${_sfx} \
        libsdl3-image-dev${_sfx} \
        libsdl3-ttf-dev${_sfx} \
        libseat-dev${_sfx} \
        libserialport-dev${_sfx} \
        libshaderc-dev${_sfx} \
        libshaderc1${_sfx} \
        libslirp-dev${_sfx} \
        libsndfile1-dev${_sfx} \
        libsoundtouch-dev${_sfx} \
        libspirv-cross-c-shared-dev${_sfx} \
        libspirv-cross-c-shared0${_sfx} \
        libsqlite3-dev${_sfx} \
        libssl-dev${_sfx} \
        libstdc++6${_sfx} \
        libswresample-dev${_sfx} \
        libswscale-dev${_sfx} \
        libtheora-dev${_sfx} \
        libudev-dev${_sfx} \
        libusb-1.0-0-dev${_sfx} \
        libvorbis-dev${_sfx} \
        libvpx-dev${_sfx} \
        libvulkan-dev${_sfx} \
        libwayland-dev${_sfx} \
        libwayland-egl-backend-dev${_sfx} \
        libwebp-dev${_sfx} \
        libwxgtk3.2-dev${_sfx} \
        libx11-dev${_sfx} \
        libx11-xcb-dev${_sfx} \
        libxcb-composite0-dev${_sfx} \
        libxcb-errors-dev${_sfx} \
        libxcb-ewmh-dev${_sfx} \
        libxcb-icccm4-dev${_sfx} \
        libxcb-keysyms1-dev${_sfx} \
        libxcb-render0-dev${_sfx} \
        libxcb-res0-dev${_sfx} \
        libxcb-xfixes0-dev${_sfx} \
        libxcomposite-dev${_sfx} \
        libxcursor-dev${_sfx} \
        libxdamage-dev${_sfx} \
        libxext-dev${_sfx} \
        libxfixes-dev${_sfx} \
        libxi-dev${_sfx} \
        libxinerama-dev${_sfx} \
        libxkbcommon-dev${_sfx} \
        libxkbcommon-x11-dev${_sfx} \
        libxml2-dev${_sfx} \
        libxmu-dev${_sfx} \
        libxrandr-dev${_sfx} \
        libxrender-dev${_sfx} \
        libxres-dev${_sfx} \
        libxss-dev${_sfx} \
        libxtst-dev${_sfx} \
        libxxf86vm-dev${_sfx} \
        libyaml-cpp-dev${_sfx} \
        libyaml-dev${_sfx} \
        libzarchive-dev${_sfx} \
        libzip-dev${_sfx} \
        libzstd-dev${_sfx} \
        portaudio19-dev${_sfx} \
        qtbase5-dev${_sfx} \
        qt6-base-dev${_sfx} \
        qt6-base-private-dev${_sfx} \
        qt6-multimedia-dev${_sfx} \
        qt6-svg-dev${_sfx} \
        qt6-tools-dev${_sfx} \
        qt6-wayland${_sfx} \
        qt6-websockets-dev${_sfx} \
        tcl-dev${_sfx} \
        zlib1g-dev${_sfx} \
    && rm -rf /var/lib/apt/lists/*

# ── Step 4b: restore tools removed by arm64 package install ──────────────────
# Installing :arm64 multiarch packages removes several amd64-only host tools:
# - gcc/g++/binutils-aarch64-linux-gnu (cross-compiler + cross-linker)
# - glslang-tools (GLSL validator binary, cmake targets reference /usr/bin/glslang)
# - python3 + helpers (python3-tomli, python3-yaml, python3.13-venv)
# - llvm-19-dev / llvm-19-tools
# - ffmpeg
# Re-install all of them after the arm64 package step.
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends \
            gcc-aarch64-linux-gnu \
            g++-aarch64-linux-gnu \
            glslang-tools \
            python3 \
            python3-pip \
            python3-tomli \
            python3-yaml \
            python3.13-venv \
            llvm-19-dev \
            llvm-19-tools \
            ffmpeg \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# ── Step 5: amd64-only extras ─────────────────────────────────────────────────
RUN if [ "${TARGETARCH}" = "amd64" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends \
            gcc-multilib \
            libc6-dev-i386 \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# ── Step 6: LLVM 21 host toolchain (always amd64) ────────────────────────────
RUN curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key \
        -o /etc/apt/trusted.gpg.d/llvm.asc \
    && echo "deb https://apt.llvm.org/trixie/ llvm-toolchain-trixie-21 main" \
        > /etc/apt/sources.list.d/llvm-21.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        clang-21 \
        lld-21 \
        llvm-21 \
        libc++-21-dev \
        libc++abi-21-dev \
        libxinerama-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Step 7: Rust via rustup ───────────────────────────────────────────────────
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain 1.88.0

ENV PATH="/root/.cargo/bin:${PATH}"

# For arm64: add the aarch64 cross-compilation target and configure the linker.
RUN if [ "${TARGETARCH}" = "arm64" ]; then \
        /root/.cargo/bin/rustup target add aarch64-unknown-linux-gnu; \
        mkdir -p /root/.cargo; \
        printf '[target.aarch64-unknown-linux-gnu]\nlinker = "aarch64-linux-gnu-gcc"\n' \
            >> /root/.cargo/config.toml; \
    fi

# ── Step 8: cmake and meson wrappers ─────────────────────────────────────────
# When ARCH=arm64 these wrappers transparently inject the toolchain/cross files
# so emulator build scripts need no per-script changes for cmake/meson.
COPY docker/emulators/aarch64-toolchain.cmake /opt/hippos/aarch64-toolchain.cmake
COPY docker/emulators/aarch64-cross.ini       /opt/hippos/aarch64-cross.ini

RUN printf '#!/bin/bash\n\
_cmake=/usr/bin/cmake\n\
if [ "${ARCH:-}" != "arm64" ]; then exec "${_cmake}" "$@"; fi\n\
# Skip for non-configure steps\n\
for _a in "$@"; do\n\
    case "${_a}" in --build|--install|-E|-P) exec "${_cmake}" "$@";; esac\n\
done\n\
# Skip if a toolchain is already explicitly provided\n\
for _a in "$@"; do\n\
    case "${_a}" in --toolchain|-DCMAKE_TOOLCHAIN_FILE*) exec "${_cmake}" "$@";; esac\n\
done\n\
exec "${_cmake}" --toolchain /opt/hippos/aarch64-toolchain.cmake "$@"\n' \
    > /usr/local/bin/cmake && chmod +x /usr/local/bin/cmake

RUN printf '#!/bin/bash\n\
_meson=/usr/bin/meson\n\
if [ "${ARCH:-}" != "arm64" ] || [ "${1:-}" != "setup" ]; then exec "${_meson}" "$@"; fi\n\
for _a in "$@"; do\n\
    [ "${_a}" = "--cross-file" ] && exec "${_meson}" "$@"\n\
done\n\
exec "${_meson}" "$@" --cross-file /opt/hippos/aarch64-cross.ini\n' \
    > /usr/local/bin/meson && chmod +x /usr/local/bin/meson
