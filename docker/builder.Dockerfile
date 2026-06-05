FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bc \
        bison \
        btrfs-progs \
        build-essential \
        ca-certificates \
        cpio \
        curl \
        debhelper \
        dosfstools \
        dwarves \
        e2fsprogs \
        fakeroot \
        fdisk \
        flex \
        git \
        gnupg \
        grub2-common \
        grub-efi-amd64-bin \
        grub-pc-bin \
        kmod \
        kpartx \
        libdw-dev \
        libelf-dev \
        libssl-dev \
        linux-image-amd64 \
        lsb-release \
        mmdebstrap \
        parted \
        python3 \
        python3-yaml \
        rsync \
        squashfs-tools \
        sudo \
        systemd-container \
        udev \
        xz-utils \
        zstd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /repo
