FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive
ENV DEBCONF_NONINTERACTIVE_SEEN=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        autoconf \
        automake \
        libtool \
        git \
        cmake \
        ninja-build \
        meson \
        pkg-config \
        python3 \
        python3-pip \
        curl \
        wget \
        ca-certificates \
        unzip \
        tar \
        xz-utils \
        zstd \
        file \
        rsync \
        patchelf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
