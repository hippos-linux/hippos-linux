FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

ARG TARGETARCH=amd64

ARG ES_DEV_PACKAGES="\
        libsdl2-dev \
        libsdl2-mixer-dev \
        libfreeimage-dev \
        libfreetype-dev \
        libcurl4-openssl-dev \
        libpugixml-dev \
        libvlc-dev \
        libgl-dev \
        libgles2-mesa-dev \
        libasound2-dev \
        libpulse-dev \
        libudev-dev \
        libboost-locale-dev \
        libboost-system-dev \
        libboost-date-time-dev"

RUN set -e; \
    if [ "${TARGETARCH}" = "amd64" ]; then \
        dev_packages="${ES_DEV_PACKAGES} build-essential vlc-plugin-base"; \
    else \
        dpkg --add-architecture arm64; \
        dev_packages="$(printf '%s:arm64 ' ${ES_DEV_PACKAGES}) gcc-aarch64-linux-gnu g++-aarch64-linux-gnu"; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        cmake \
        make \
        git \
        curl \
        ca-certificates \
        pkg-config \
        gettext \
        rapidjson-dev \
        ${dev_packages}; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /work
