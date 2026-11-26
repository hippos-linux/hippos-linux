#!/usr/bin/env python3
"""Usage: hippos-romm-ps3-install install <folder> <game.psn>
       hippos-romm-ps3-install install-addons <folder>
       hippos-romm-ps3-install uninstall <game.psn>

Installs PS3 packages downloaded from RomM into RPCS3.
install: a PSN game's .pkg files (game, updates, DLC) and licenses (.rap, .edat) from <folder>, then
  writes the game's title id to <game.psn> and deletes <folder>.
install-addons: updates and DLC for a disc game (<folder> sits next to <name>.iso or <name>.ps3).
uninstall: removes the installed game and its licenses; saves are kept.
Exit status: 0 done, 1 usage, 2 no package or title id, 3 installation failed. The last line says what happened.
"""
from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from HipposPaths import CACHE, CONFIGS
from emulatorlauncher_rpcs3 import RPCS3_HDD0, _write_rpcs3_vfs
from emulatorlauncher_shared import _find_emulator_bin

EXDATA = RPCS3_HDD0 / 'home' / '00000001' / 'exdata'
INSTALL_LOG = Path('/userdata/system/logs/romm-ps3-install.log')
RPCS3_LOG = CACHE / 'rpcs3' / 'RPCS3.log'
LOCKS = RPCS3_HDD0 / 'game' / '＄locks'
CONTENT_ID = re.compile(r'^[A-Z0-9]{6}-[A-Z]{4}\d{5}_\d{2}-[A-Z0-9_]{16}$')
TITLE_ID = re.compile(r'^[A-Z]{4}\d{5}$')
KIND_ORDER = {'base': 1, 'update': 2, 'dlc': 3, 'other': 4}
DISC_PACKAGE_GLOBS = ('PS3_GAME/INSDIR/*.PKG', 'PS3_GAME/PKGDIR/PKG*/INSTALL.PKG', 'PS3_EXTRA/D*/DATA000.PKG')


class Failure(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Package:
    path: Path
    kind: str
    content_id: str
    drm: int
    version: str
    label: str

    @property
    def title_id(self) -> str:
        return self.content_id[7:16]


def read_package(path: Path, label: str = '') -> Package | None:
    with path.open('rb') as f:
        header = f.read(4096)
    if header[:4] != b'\x7fPKG':
        return None
    content_id = header[0x30:0x30 + 36].rstrip(b'\0').decode('ascii', 'replace')
    if not CONTENT_ID.match(content_id):
        return None
    offset, count = struct.unpack('>II', header[8:16])
    drm = content_type = flags = 0
    version = '00.00'
    for _ in range(count):
        if offset + 8 > len(header):
            break
        packet_id, size = struct.unpack('>II', header[offset:offset + 8])
        data = header[offset + 8:offset + 8 + size]
        value = struct.unpack('>I', data[:4])[0] if len(data) >= 4 else 0
        if packet_id == 1:
            drm = value
        elif packet_id == 2:
            content_type = value
        elif packet_id == 3:
            flags = value
        elif packet_id == 8 and size == 8:
            version = f'{data[6]:02x}.{data[7]:02x}'
        offset += 8 + size
    if flags & 0x10 and content_type in (4, 5):
        kind = 'update'
    else:
        kind = {5: 'base', 4: 'dlc'}.get(content_type, 'other')
    return Package(path, kind, content_id, drm, version, label or path.name)


def sfo_value(path: Path, key: str) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ''
    if data[:4] != b'\0PSF':
        return ''
    keys, values, count = struct.unpack('<III', data[8:20])
    for i in range(count):
        key_offset, _, length, _, value_offset = struct.unpack('<HHIII', data[20 + i * 16:36 + i * 16])
        name = data[keys + key_offset:data.index(b'\0', keys + key_offset)].decode()
        if name == key:
            return data[values + value_offset:values + value_offset + length].rstrip(b'\0').decode()
    return ''


def version_number(version: str) -> int:
    return int(version.replace('.', '') or 0)


@dataclass
class Disc:
    title_id: str = ''
    version: str = ''
    packages: tuple[Package, ...] = ()
    lock: Path | None = None


@contextmanager
def disc_beside(folder: Path):
    base = folder.with_suffix('')
    mount_dir = None
    if (base.with_suffix('.ps3')).is_dir():
        root = base.with_suffix('.ps3')
    elif (base.with_suffix('.iso')).is_file():
        mount_dir = Path(tempfile.mkdtemp())
        if subprocess.run(['sudo', '-n', 'mount', '-o', 'loop,ro', str(base.with_suffix('.iso')), str(mount_dir)],
                          capture_output=True).returncode != 0:
            mount_dir.rmdir()
            print(f'Warning: cannot read {base.with_suffix(".iso").name}, the packages on the disc are not checked')
            yield Disc()
            return
        root = mount_dir
    else:
        yield Disc()
        return
    try:
        sfo = root / 'PS3_GAME' / 'PARAM.SFO'
        title_id, version = sfo_value(sfo, 'TITLE_ID'), sfo_value(sfo, 'APP_VER')
        if not TITLE_ID.match(title_id):
            yield Disc()
            return
        lock = LOCKS / f'{title_id}_v{version}'
        if lock.exists() or (RPCS3_HDD0 / 'game' / '.locks' / title_id).exists():
            yield Disc(title_id, version)
            return
        found = [read_package(p, f'disc {p.relative_to(root)}') for pattern in DISC_PACKAGE_GLOBS for p in sorted(root.glob(pattern))]
        packages = tuple(p for p in found if p is not None)
        yield Disc(title_id, version, packages, lock if packages else None)
    finally:
        if mount_dir is not None:
            subprocess.run(['sudo', '-n', 'umount', str(mount_dir)], capture_output=True)
            mount_dir.rmdir()


def install_package(rpcs3: Path, package: Package, disc: Disc) -> str:
    if package.kind == 'update':
        installed = sfo_value(RPCS3_HDD0 / 'game' / package.title_id / 'PARAM.SFO', 'APP_VER')
        if not installed and package.title_id == disc.title_id:
            installed = disc.version
        if installed and version_number(installed) >= version_number(package.version):
            print(f'Skipping update {package.version}: {package.label} ({package.title_id} is already at {installed})')
            return 'skipped'
    print(f'Installing {package.kind} {package.version}: {package.label}')
    RPCS3_LOG.unlink(missing_ok=True)
    env = {**os.environ, 'XDG_CONFIG_HOME': str(CONFIGS), 'XDG_CACHE_HOME': str(CACHE)}
    subprocess.run([str(rpcs3), '--headless', '--installpkg', str(package.path)], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rpcs3_log = RPCS3_LOG.read_text(errors='replace') if RPCS3_LOG.exists() else ''
    INSTALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with INSTALL_LOG.open('a') as log:
        log.write(f'===== {package.path}\n')
        log.writelines(line + '\n' for line in rpcs3_log.splitlines()
                       if re.search(r'PKG:|GUI:|SYS: (Firmware|Option)|·[EF] ', line) and not re.search(r'PKG: (Entry|Created)', line))
    if f'Successfully installed {package.path} ' not in rpcs3_log:
        print(f'Failed: {package.label} (see {INSTALL_LOG})')
        return 'failed'
    if package.kind == 'update':
        installed = sfo_value(RPCS3_HDD0 / 'game' / package.title_id / 'PARAM.SFO', 'APP_VER')
        if installed != package.version:
            print(f'Failed: {package.label} is {package.version} but {package.title_id} is at {installed or "no version"} (see {INSTALL_LOG})')
            return 'failed'
    return 'installed'


def install_packages(folder: Path, disc: Disc, need_base: bool) -> tuple[str, dict[str, int]]:
    packages = list(disc.packages)
    missing_licences: list[str] = []
    for path in sorted(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() == '.pkg'):
        package = read_package(path)
        if package is None:
            print(f'Skipped, not a PS3 package: {path.name}')
            continue
        packages.append(package)
        if package.drm in (1, 2) and not any(folder.rglob(f'{package.content_id}.[rR][aA][pP]')):
            if package.kind in ('base', 'update'):
                print(f'Missing license {package.content_id}.rap for {path.name}')
                if f'{package.content_id}.rap' not in missing_licences:
                    missing_licences.append(f'{package.content_id}.rap')
            else:
                print(f'Warning: no license {package.content_id}.rap for {path.name}')
    if not packages:
        raise Failure(2, f'No PS3 package in {folder}')
    if missing_licences:
        raise Failure(3, f'Installation failed, {folder} kept: missing license {" ".join(missing_licences)}')
    base_id = next((p.title_id for p in packages if p.kind == 'base'), '')
    if need_base and not base_id:
        raise Failure(2, f'No game package in {folder}')

    rpcs3 = _find_emulator_bin('rpcs3')
    if rpcs3 is None:
        raise Failure(3, 'Installation failed: RPCS3 is not installed')
    _write_rpcs3_vfs()
    EXDATA.mkdir(parents=True, exist_ok=True)
    for licence in folder.rglob('*'):
        if licence.is_file() and licence.suffix.lower() in ('.rap', '.edat'):
            name = licence.stem + '.rap' if licence.suffix.lower() == '.rap' else licence.name
            shutil.copyfile(licence, EXDATA / name)

    counts = {'base': 0, 'update': 0, 'dlc': 0, 'skipped': 0, 'failed': 0}
    for package in sorted(packages, key=lambda p: (KIND_ORDER[p.kind], p.title_id, p.version)):
        result = install_package(rpcs3, package, disc)
        if result == 'installed':
            counts['base' if package.kind == 'base' else 'update' if package.kind == 'update' else 'dlc'] += 1
        else:
            counts[result] += 1
            if result == 'failed' and package.kind in ('base', 'update'):
                break
    return base_id, counts


def install(folder: Path, psn: Path) -> str:
    if not folder.is_dir():
        raise Failure(1, f'No folder {folder}')
    base_id, n = install_packages(folder, Disc(), need_base=True)
    if n['failed']:
        raise Failure(3, f'Installation failed, {folder} kept ({n["base"]} game, {n["update"]} updates, {n["dlc"]} DLC installed)')
    if not (RPCS3_HDD0 / 'game' / base_id / 'USRDIR' / 'EBOOT.BIN').is_file():
        raise Failure(3, f'Installation failed: no {base_id}/USRDIR/EBOOT.BIN')
    tmp = psn.with_name(psn.name + '.tmp')
    tmp.write_text(base_id + '\n')
    tmp.replace(psn)
    shutil.rmtree(folder)
    return f'Installed {base_id} ({n["base"]} game, {n["update"]} updates, {n["dlc"]} DLC packages, {n["skipped"]} already installed)'


def install_addons(folder: Path) -> str:
    if not folder.is_dir():
        raise Failure(1, f'No folder {folder}')
    with disc_beside(folder) as disc:
        _, n = install_packages(folder, disc, need_base=False)
        if n['failed']:
            raise Failure(3, f'Installation failed, {folder} kept ({n["update"]} updates, {n["dlc"]} DLC installed)')
        if disc.lock is not None:
            disc.lock.parent.mkdir(parents=True, exist_ok=True)
            disc.lock.touch()
    shutil.rmtree(folder)
    return f'Installed {n["update"]} updates, {n["dlc"]} DLC packages, {n["skipped"]} already installed'


def uninstall(psn: Path) -> str:
    if not psn.is_file():
        raise Failure(1, f'No file {psn}')
    title_id = next((line.strip().upper() for line in psn.read_text().splitlines() if len(line.strip()) >= 9), '')
    if not TITLE_ID.match(title_id):
        raise Failure(2, f'No title id in {psn}')
    shutil.rmtree(RPCS3_HDD0 / 'game' / title_id, ignore_errors=True)
    for licence in EXDATA.glob(f'*-{title_id}_*'):
        licence.unlink()
    return f'Uninstalled {title_id}'


def main(argv: list[str]) -> int:
    commands = {'install': (install, 2), 'install-addons': (install_addons, 1), 'uninstall': (uninstall, 1)}
    command = commands.get(argv[1] if len(argv) > 1 else '')
    if command is None or len(argv) != command[1] + 2:
        print('\n'.join(__doc__.splitlines()[:3]))
        return 1
    try:
        print(command[0](*map(Path, argv[2:])))
    except Failure as failure:
        print(failure)
        return failure.status
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
