from __future__ import annotations

import os
import subprocess
from pathlib import Path

IMAGE_PACKAGES = Path('/usr/share/hippos/image-packages.list')
USER_PACKAGES = Path('/userdata/system/apt-packages.list')
RESTORE_PENDING = Path('/var/lib/hippos/apt-restore-pending')
PRE_UPDATE_STATUS = Path('/var/lib/hippos/pre-update-dpkg-status')
PRE_UPDATE_EXTENDED_STATES = Path('/var/lib/hippos/pre-update-apt-extended-states')

_APT = ['apt-get', '-o', 'DPkg::Lock::Timeout=300']
_APT_INSTALL = [*_APT, 'install', '-y', '-o', 'Dpkg::Options::=--force-confold']
_APT_ENV = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}

def image_packages() -> frozenset[str] | None:
    try:
        return frozenset(IMAGE_PACKAGES.read_text(encoding='utf-8').split())
    except FileNotFoundError:
        return None

def installed_user_packages(image: frozenset[str]) -> list[str]:
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

def owning_package(path: Path) -> str | None:
    result = subprocess.run(['dpkg-query', '-S', str(path)], capture_output=True, text=True, check=False)
    if result.returncode != 0 or ':' not in result.stdout:
        return None
    return result.stdout.split(':', 1)[0].split(',')[0].strip()

def missing_packages(packages: list[str]) -> list[str]:
    result = subprocess.run(
        ['dpkg-query', '-W', '-f', '${Package}:${Architecture} ${db:Status-Status}\\n', *packages],
        capture_output=True, text=True, check=False,
    )
    installed = set()
    for line in result.stdout.splitlines():
        name, _, status = line.partition(' ')
        if status == 'installed':
            installed.update((name.partition(':')[0], name))
    return [p for p in packages if p not in installed]

def install_packages(packages: list[str], root: str | None = None) -> tuple[bool, list[str]]:
    prefix = ['chroot', root] if root else []
    updated = subprocess.run([*prefix, *_APT, 'update'], env=_APT_ENV).returncode == 0
    if subprocess.run([*prefix, *_APT_INSTALL, *packages], env=_APT_ENV).returncode == 0:
        return updated, []
    failed = [p for p in packages
              if subprocess.run([*prefix, *_APT_INSTALL, p], env=_APT_ENV).returncode != 0]
    return updated, failed
