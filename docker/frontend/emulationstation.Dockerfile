FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        curl \
        ca-certificates \
        pkg-config \
        gettext \
        libsdl2-dev \
        libsdl2-mixer-dev \
        libfreeimage-dev \
        libfreetype-dev \
        libcurl4-openssl-dev \
        libpugixml-dev \
        rapidjson-dev \
        libvlc-dev \
        vlc-plugin-base \
        libgl-dev \
        libgles2-mesa-dev \
        libasound2-dev \
        libpulse-dev \
        libudev-dev \
        libboost-locale-dev \
        libboost-system-dev \
        libboost-date-time-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
