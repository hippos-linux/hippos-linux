from __future__ import annotations

import io
import os
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ElementTree
import zipfile
from pathlib import Path

VERSION = '1.09'
DOWNLOAD_URL = f'https://www.sindenlightgun.com/software/SindenLightgunSoftwareReleaseV{VERSION}.zip'
ARCHIVE_DIR = (f'SindenLightgunSoftwareReleaseV{VERSION}/SindenLightgunLinuxSoftwareV{VERSION}'
               '/X86/64bit/Lightgun/Player1/')
INSTALL_DIR = Path('/userdata/system/sinden')
LIBRARY_DIR = Path('/usr/lib/hippos/sinden')
CONFIG_NAME = 'LightgunMono.exe.config'

RECOIL = {
    'gun':              {'EnableRecoil': '1', 'TriggerRecoilNormalOrRepeat': '1', 'AutoRecoilStrength': '100',
                         'AutoRecoilStartDelay': '150', 'AutoRecoilDelayBetweenPulses': '10'},
    'gun-quiet':        {'EnableRecoil': '1', 'TriggerRecoilNormalOrRepeat': '1', 'AutoRecoilStrength': '40',
                         'AutoRecoilStartDelay': '150', 'AutoRecoilDelayBetweenPulses': '10'},
    'machinegun':       {'EnableRecoil': '1', 'TriggerRecoilNormalOrRepeat': '1', 'AutoRecoilStrength': '100',
                         'AutoRecoilStartDelay': '1', 'AutoRecoilDelayBetweenPulses': '10'},
    'machinegun-quiet': {'EnableRecoil': '1', 'TriggerRecoilNormalOrRepeat': '1', 'AutoRecoilStrength': '40',
                         'AutoRecoilStartDelay': '1', 'AutoRecoilDelayBetweenPulses': '10'},
}
BORDER_4_3 = {'OffsetX': '12.5', 'OffsetXRatio': '0.75', 'OffsetY': '0', 'OffsetYRatio': '1'}
BORDER_FULL = {'OffsetX': '0', 'OffsetXRatio': '1', 'OffsetY': '0', 'OffsetYRatio': '1'}
CAMERA_SETTINGS = {'contrast': 'CameraContrast', 'brightness': 'CameraBrightness', 'exposure': 'CameraExposure'}


def setting(key: str) -> str:
    return subprocess.run(['hippos-settings', 'get', key], capture_output=True, text=True).stdout.strip()


def install() -> None:
    marker = INSTALL_DIR / 'version'
    if marker.is_file() and marker.read_text().strip() == VERSION:
        return
    with urllib.request.urlopen(DOWNLOAD_URL, timeout=60) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    staging = INSTALL_DIR.with_name('sinden.new')
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    for member in archive.namelist():
        if member.startswith(ARCHIVE_DIR) and member != ARCHIVE_DIR and not member.endswith('/'):
            (staging / Path(member).name).write_bytes(archive.read(member))
    (staging / 'version').write_text(f'{VERSION}\n')
    shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    staging.rename(INSTALL_DIR)


def find_under(parent: Path, pattern: str, wanted=lambda node: True) -> Path | None:
    for node in sorted(Path('/sys/class').glob(pattern)):
        if str((node / 'device').resolve()).startswith(f'{parent}/') and wanted(node):
            return node
    return None


def camera_and_serial(parent: Path) -> tuple[str, str] | None:
    camera = find_under(parent, 'video4linux/video*', lambda node: (node / 'index').read_text().strip() == '0')
    serial = find_under(parent, 'tty/ttyACM*')
    return (f'/dev/{camera.name}', f'/dev/{serial.name}') if camera and serial else None


def write_config(path: Path, camera: str, serial: str) -> None:
    values = {'VideoDevice': camera, 'SerialPortWrite': serial}
    values |= BORDER_4_3 if setting('controllers.guns.bordersratio') == '4:3' else BORDER_FULL
    values |= RECOIL.get(setting('controllers.guns.recoil'), {'EnableRecoil': '0'})
    for name, key in CAMERA_SETTINGS.items():
        if value := setting(f'controllers.guns.sinden.{name}'):
            values[key] = value
    tree = ElementTree.parse(path)
    for entry in tree.getroot().iter('add'):
        if entry.get('key') in values:
            entry.set('value', values[entry.get('key')])
    tree.write(path, encoding='utf-8', xml_declaration=True)


def start(parent: Path, run_dir: Path) -> subprocess.Popen | None:
    if shutil.which('mono') is None:
        raise SystemExit('hippos-lightgun: Sinden light guns need the PC (x86-64) version of HippOS')
    devices = camera_and_serial(parent)
    if devices is None:
        return None
    install()
    shutil.rmtree(run_dir, ignore_errors=True)
    shutil.copytree(INSTALL_DIR, run_dir)
    write_config(run_dir / CONFIG_NAME, *devices)
    return subprocess.Popen(['mono', 'LightgunMono.exe'], cwd=run_dir,
                            env={**os.environ, 'LD_LIBRARY_PATH': str(LIBRARY_DIR)})
