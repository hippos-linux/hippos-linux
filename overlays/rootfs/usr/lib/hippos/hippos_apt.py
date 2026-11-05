"""Packages the user installed with apt, as opposed to ones shipped in the image.

Apt installs land in the persistent overlay upper layer. On boot into a new
deployment the initramfs (hippos-overlay) clears package state from that layer,
since it would hide the new image's, and hippos-apt-packages reinstalls the
recorded list.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Written by build/configure-rootfs.sh after the image's last package install.
IMAGE_PACKAGES = Path('/usr/share/hippos/image-packages.list')
USER_PACKAGES = Path('/userdata/system/apt-packages.list')
# Created by hippos-overlay when it clears package state; removed once
# hippos-apt-packages has reinstalled USER_PACKAGES.
RESTORE_PENDING = Path('/var/lib/hippos/apt-restore-pending')
# The cleared dpkg status and apt marks, saved alongside the flag. Only used
# when USER_PACKAGES doesn't exist yet (systems from before it was recorded).
PRE_UPDATE_STATUS = Path('/var/lib/hippos/pre-update-dpkg-status')
PRE_UPDATE_EXTENDED_STATES = Path('/var/lib/hippos/pre-update-apt-extended-states')


def image_packages() -> frozenset[str] | None:
    """None outside a built image (e.g. inside the build chroot)."""
    try:
        return frozenset(IMAGE_PACKAGES.read_text(encoding='utf-8').split())
    except FileNotFoundError:
        return None


def installed_user_packages(image: frozenset[str]) -> list[str]:
    """Manually installed packages that aren't part of the image.
    Names carry an arch suffix only for foreign arches (foo:i386), matching
    image-packages.list."""
    manual = subprocess.run(
        ['apt-mark', 'showmanual'], capture_output=True, text=True, check=True,
    ).stdout.split()
    return sorted(p for p in manual if p not in image)


def recorded_user_packages() -> list[str]:
    try:
        return USER_PACKAGES.read_text(encoding='utf-8').split()
    except FileNotFoundError:
        return []


def _deb822(path: Path) -> list[dict[str, str]]:
    """Paragraphs of a dpkg status / apt extended_states file (first line of each field)."""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except FileNotFoundError:
        return []
    paragraphs = []
    for block in text.split('\n\n'):
        fields = {}
        for line in block.splitlines():
            if line and not line[0].isspace() and ':' in line:
                key, _, value = line.partition(':')
                fields[key] = value.strip()
        if fields:
            paragraphs.append(fields)
    return paragraphs


def pre_update_user_packages(image: frozenset[str]) -> list[str]:
    """Best guess at the user's packages from the saved pre-update dpkg status:
    installed, not marked automatically installed, and not in the current image.
    Packages the previous image had and this one dropped also show up here."""
    native = subprocess.run(
        ['dpkg', '--print-architecture'], capture_output=True, text=True, check=True,
    ).stdout.strip()

    def name(fields: dict[str, str]) -> str:
        arch = fields.get('Architecture', native)
        return fields['Package'] if arch in (native, 'all') else f"{fields['Package']}:{arch}"

    auto = {
        name(f) for f in _deb822(PRE_UPDATE_EXTENDED_STATES)
        if 'Package' in f and f.get('Auto-Installed') == '1'
    }
    installed = {
        name(f) for f in _deb822(PRE_UPDATE_STATUS)
        if 'Package' in f and f.get('Status', '').endswith(' installed')
    }
    return sorted(installed - auto - image)


def package_files(package: str) -> list[Path]:
    result = subprocess.run(['dpkg-query', '-L', package], capture_output=True, text=True, check=False)
    return [Path(line) for line in result.stdout.splitlines() if line.startswith('/')]
