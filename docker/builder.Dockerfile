FROM debian:trixie

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bc \
        bmap-tools \
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
        gcc-aarch64-linux-gnu \
        g++-aarch64-linux-gnu \
        binutils-aarch64-linux-gnu \
        qemu-user-static \
        binfmt-support \
        kmod \
        kpartx \
        libdw-dev \
        libelf-dev \
        libssl-dev \
        lsb-release \
        mmdebstrap \
        parted \
        python3 \
        python3-ruamel.yaml \
        python3-yaml \
        rsync \
        squashfs-tools \
        sudo \
        systemd-container \
        udev \
        xz-utils \
        zstd \
    && rm -rf /var/lib/apt/lists/*

# The repo is bind-mounted host-owned (see relaunch_in_docker) but this
# container always runs as root — git refuses to touch it ("detected
# dubious ownership") without this, and build-rootfs.sh's `git rev-parse
# HEAD 2>/dev/null || echo unknown` silently swallows that failure, so
# every release's /etc/hippos-version has shipped with GIT_COMMIT=unknown
# instead of a real commit hash.
RUN git config --system --add safe.directory /work

WORKDIR /repo
