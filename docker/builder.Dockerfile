FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        btrfs-progs \
        ca-certificates \
        curl \
        dosfstools \
        e2fsprogs \
        fdisk \
        git \
        gnupg \
        grub2-common \
        grub-efi-amd64-bin \
        grub-pc-bin \
        kmod \
        kpartx \
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
