#!/usr/bin/env python3
"""HippOS emulator launcher — routes ES game launches to the right emulator."""

from __future__ import annotations

import argparse
import configparser
import filecmp
import json
import logging
import os
import re
import subprocess
import sys
import time
import shutil
import zipfile
import tomllib
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from shutil import copyfile, which
from typing import Callable, Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

try:
    import hippos_switchres as _switchres
    _HAS_SWITCHRES = True
except ImportError:
    _HAS_SWITCHRES = False

from hippos_squashfs import mount_squashfs
from hippos_overlayfs import mount_overlayfs
from hippos_bezels import prepare_bezel
from hippos_evmapy import evmapy_context
from hippos_controller_monitor import start_controller_monitor

# ── Paths ──────────────────────────────────────────────────────────────────────

from HipposPaths import (  # noqa: E402
    USERDATA, HOME, CONFIGS, SAVES, BIOS, SCREENSHOTS, CACHE, LOGS,
    HIPPOS_CONF, HIPPOS_SHARE_DIR, DEFAULTS_DIR, HIPPOS_SHADERS,
    USER_ES_DIR,
)

RA_CONFIG_DIR = CONFIGS / 'retroarch'
RA_CUSTOM_CFG = RA_CONFIG_DIR / 'retroarchcustom.cfg'
RA_CORES_CFG  = RA_CONFIG_DIR / 'cores' / 'retroarch-core-options.cfg'

RETROARCH_BIN = Path('/usr/bin/retroarch')

PLAY_CONFIG_DIR = CONFIGS / 'play'
PLAY_DATA_DIR = PLAY_CONFIG_DIR / 'Play Data Files'
PLAY_CONFIG_FILE = PLAY_DATA_DIR / 'config.xml'
PLAY_INPUT_FILE = PLAY_DATA_DIR / 'inputprofiles' / 'default.xml'
PLAY_SAVES_DIR = SAVES / 'ps2'

AMIBERRY_CONFIG_DIR = CONFIGS / 'amiberry'
AMIBERRY_CONF = AMIBERRY_CONFIG_DIR / 'amiberry.conf'
AMIBERRY_RETROARCH_DIR = AMIBERRY_CONFIG_DIR / 'retroarch'
AMIBERRY_OVERLAY_CFG = AMIBERRY_RETROARCH_DIR / 'overlay.cfg'
AMIBERRY_INPUTS_DIR = AMIBERRY_RETROARCH_DIR / 'inputs'
AMIBERRY_PLUGINS_DIR = AMIBERRY_CONFIG_DIR / 'plugins'
AMIBERRY_WHDBOOT_DIR = AMIBERRY_CONFIG_DIR / 'whdboot'
AMIBERRY_SAVES_DIR = SAVES / 'amiga'
AMIBERRY_SCREENSHOTS_DIR = SCREENSHOTS
AMIBERRY_BIOS_DIR = BIOS / 'amiga'
AMIBERRY_LOG_FILE = LOGS / 'amiberry.log'
AMIBERRY_DATA_DIR = Path('/usr/share/amiberry/data')

GSPLUS_CONFIG_DIR = CONFIGS / 'GSplus'
GSPLUS_CONFIG_FILE = GSPLUS_CONFIG_DIR / 'config.txt'

VPINBALL_CONFIG_DIR = CONFIGS / 'vpinball'
VPINBALL_INI = VPINBALL_CONFIG_DIR / 'VPinballX.ini'
VPINBALL_LOG = VPINBALL_CONFIG_DIR / 'vpinball.log'
VPINBALL_PINMAME_INI = VPINBALL_CONFIG_DIR / 'pinmame' / 'ini'
VPINBALL_DEFAULT_INI = Path('/usr/bin/vpinball/assets/Default_VPinballX.ini')

XEMU_CONFIG_DIR = CONFIGS / 'xemu'
XEMU_CONFIG_FILE = XEMU_CONFIG_DIR / 'xemu.toml'
XEMU_SAVES_DIR = SAVES / 'xbox'
XEMU_DATA_DIRS = (Path('/opt/emulators/xemu/data'), Path('/usr/share/xemu/data'))

OPENBOR_CONFIG_DIR = CONFIGS / 'openbor'
OPENBOR_SAVE_DIR = SAVES / 'openbor'
OPENBOR_ROM_DIR = USERDATA / 'roms' / 'openbor'
OPENBOR_CONFIG_FILES = {
    'openbor4432': 'config4432.ini',
    'openbor6412': 'config6412.ini',
    'openbor7142': 'config7142.ini',
    'openbor7530': 'config7530.ini',
}
OPENBOR_BINARIES = {
    'openbor4432': 'OpenBOR4432',
    'openbor6412': 'OpenBOR6412',
    'openbor7142': 'OpenBOR7142',
    'openbor7530': 'OpenBOR7530',
}

MAME_CONFIG_DIR = CONFIGS / 'mame'
MAME_INI        = MAME_CONFIG_DIR / 'mame.ini'
MAME_ROMS       = USERDATA / 'roms' / 'mame'

DOLPHIN_CONFIG_DIR = CONFIGS / 'dolphin-emu'
DOLPHIN_INI        = DOLPHIN_CONFIG_DIR / 'Dolphin.ini'
DOLPHIN_GFX_INI    = DOLPHIN_CONFIG_DIR / 'GFX.ini'
DOLPHIN_QT_INI     = DOLPHIN_CONFIG_DIR / 'Qt.ini'

DUCKSTATION_CONFIG_DIR = CONFIGS / 'duckstation'
DUCKSTATION_SETTINGS   = DUCKSTATION_CONFIG_DIR / 'settings.ini'

FLYCAST_CONFIG_DIR = CONFIGS / 'flycast'
FLYCAST_EMU_CFG    = FLYCAST_CONFIG_DIR / 'emu.cfg'

MUPEN_CONFIG_DIR   = CONFIGS / 'mupen64'
MUPEN_CUSTOM       = MUPEN_CONFIG_DIR / 'mupen64plus.cfg'

SUPERMODEL_CONFIG_DIR = CONFIGS / 'supermodel'
SUPERMODEL_INI        = SUPERMODEL_CONFIG_DIR / 'Supermodel.ini'
SUPERMODEL_TEMPLATE   = Path('/usr/share/supermodel/Supermodel.ini.template')

MODEL2_RUNTIME_ROOT = USERDATA / 'emulators' / 'model2emu' / 'current'
MODEL2_RUNTIME_EMU  = MODEL2_RUNTIME_ROOT / 'emulator'
MODEL2_SOURCE_EMU   = Path('/opt/emulators/model2emu/emulator')
MODEL2_ROMS         = USERDATA / 'roms' / 'model2'

SHADPS4_CONFIG_DIR = CONFIGS / 'shadps4'
SHADPS4_USER_CONFIG_DIR = SHADPS4_CONFIG_DIR / 'user'
SHADPS4_TOML = SHADPS4_USER_CONFIG_DIR / 'config.toml'
SHADPS4_SAVES = SAVES / 'shadps4'
SHADPS4_RUNTIME_DIR = Path('/run/hippos/emulators/shadps4')
SHADPS4_BUNDLE_DIR = Path('/opt/emulators/shadps4')
SHADPS4_ROM_DIR = USERDATA / 'roms' / 'ps4'

XENIA_RUNTIME_DIR = USERDATA / 'emulators' / 'xenia' / 'current'
XENIA_CANARY_RUNTIME_DIR = USERDATA / 'emulators' / 'xenia-canary' / 'current'
XENIA_PREFIX_DIR = USERDATA / 'wine-bottles' / 'xenia' / 'current'
XENIA_CANARY_PREFIX_DIR = USERDATA / 'wine-bottles' / 'xenia-canary' / 'current'
XENIA_BUNDLE_DIR = Path('/opt/emulators/xenia/emulator')
XENIA_CANARY_BUNDLE_DIR = Path('/opt/emulators/xenia-canary/emulator')
XENIA_CACHE_DIR = CACHE / 'xenia'
XENIA_SAVES_DIR = SAVES / 'xbox360'
LINDBERGH_RUNTIME_DIR = Path('/run/hippos/emulators/lindbergh-loader')
LINDBERGH_BUNDLE_DIR = Path('/opt/emulators/lindbergh-loader')
CLK_QUICKLOAD_SYSTEMS = {'amstradcpc', 'archimedes', 'electron', 'msx1', 'msx2', 'oricatmos', 'zxspectrum'}
CLK_SVIDEO_SYSTEMS = {'colecovision', 'mastersystem'}
CLK_RGB_SYSTEMS = {'amstradcpc', 'atarist', 'electron', 'enterprise', 'msx1', 'msx2', 'oricatmos', 'zxspectrum'}
TSUGARU_CD_SYSTEMS = {'.iso', '.cue', '.bin'}

STANDALONE_BINARIES: dict[str, tuple[str, ...]] = {
    'amiberry': ('amiberry',),
    'applewin': ('qapple', 'applen', 'applewin', 'AppleWin'),
    'cemu': ('Cemu', 'cemu'),
    'easyrpg': ('easyrpg-player', 'easyrpg'),
    'hypseus-singe': ('hypseus',),
    'ikemen': ('Ikemen_GO', 'ikemen'),
    'melonds': ('melonDS', 'melonds'),
    'openbor': ('OpenBOR', 'OpenBOR7530'),
    'pcsx2': ('pcsx2-qt', 'pcsx2'),
    'ppsspp': ('PPSSPPSDL', 'ppsspp'),
    'basilisk2': ('BasiliskII', 'basilisk2'),
    'citron-neo': ('citron-neo', 'citron'),
    'clk': ('clksignal', 'clk'),
    'demul': ('demul',),
    'dosbox_staging': ('dosbox-staging', 'dosbox_staging', 'dosbox'),
    'eka2l1': ('eka2l1_qt', 'eka2l1'),
    'dosboxx': ('dosbox-x', 'dosboxx'),
    'play': ('Play', 'play'),
    'gsplus': ('GSplus', 'gsplus'),
    'samcoupe': ('samcoupe', 'simcoupe'),
    'steam': ('steam',),
    'flatpak': ('flatpak',),
    'moonlight': ('moonlight',),
    'wine': ('wine-tkg', 'wine'),
    'lightspark': ('lightspark',),
    'pyxel': ('pyxel',),
    'ruffle': ('ruffle',),
    'solarus': ('solarus-run', 'solarus'),
    'tsugaru': ('Tsugaru_CUI', 'tsugaru'),
    'x16emu': ('x16emu',),
    'xroar': ('xroar',),
    'thextech': ('thextech',),
    'yquake2': ('yquake2',),
    'desmume': ('desmume',),
    'dolphin': ('dolphin-emu', 'dolphin'),
    'dolphin-emu': ('dolphin-emu', 'dolphin'),
    'dosbox': ('dosbox',),
    'dosbox-x': ('dosbox-x',),
    'fsuae': ('fs-uae', 'fsuae'),
    'fceux': ('fceux',),
    'hatari': ('hatari',),
    'mame': ('mame',),
    'mednafen': ('mednafen',),
    'mupen64plus-qt': ('mupen64plus-qt',),
    'nestopia': ('nestopia',),
    'openmsx': ('openmsx',),
    'raze': ('raze',),
    'redream': ('redream',),
    'ryujinx': ('Ryujinx.sh', 'Ryujinx', 'ryujinx'),
    'eden': ('eden',),
    'sugarbox': ('sugarbox', 'SugarboxV2'),
    'tic80': ('tic80',),
    'vita3k': ('Vita3K', 'vita3k'),
    'vpinball': ('VPinballX_GL', 'VPinballX', 'vpinball'),
    'scummvm': ('scummvm',),
    'stella': ('stella',),
    'vice': ('x64', 'x64sc', 'xscpu64', 'xvic', 'x128', 'x64dtv', 'xplus4', 'xpet'),
    'virtualjaguar': ('virtualjaguar',),
}

ARTIFACT_PACKAGE_ALIASES: dict[str, tuple[str, ...]] = {
    'dolphin': ('dolphin-emu',),
    'dosbox_staging': ('dosbox-staging',),
    'dosboxx': ('dosbox-x',),
    'mupen64plus-qt': ('mupen64plus',),
    'pyxel': ('python-pyxel',),
    'solarus': ('solarus-engine',),
}

LIBRETRO_RATIO_INDEXES: tuple[str, ...] = (
    '4/3', '16/9', '16/10', '16/15', '21/9', '1/1', '2/1', '3/2', '3/4',
    '4/1', '9/16', '5/4', '6/5', '7/9', '8/3', '8/7', '19/12', '19/14',
    '30/17', '32/9', 'config', 'squarepixel', 'core', 'custom', 'full',
)

# Core search order: user-updated → bundled artifacts → Debian apt packages.
# find_core() also checks /opt/emulators/*/cores so package-specific libretro
# builds, such as flycast and snes9x, can be used without copying artifacts.
CORE_SEARCH_PATHS = [
    USERDATA / 'emulators' / 'retroarch' / 'current' / 'cores',
    Path('/opt/emulators/retroarch/cores'),
    USERDATA / 'emulators' / 'retroarch' / 'cores',
    Path('/usr/lib/x86_64-linux-gnu/libretro'),
    Path('/usr/lib/aarch64-linux-gnu/libretro'),
    Path('/usr/lib/libretro'),
]

LIBRETRO_CORE_ALIASES: dict[str, tuple[str, ...]] = {
    'beetle-saturn': ('mednafen_saturn',),
    'bsnes_hd': ('bsnes_hd_beta',),
    'genesis_plus_gx-wide': ('genesis_plus_gx_wide',),
    'mame078plus': ('mame2003_plus',),
    'pce': ('mednafen_pce',),
    'pce_fast': ('mednafen_pce_fast',),
    'pcfx': ('mednafen_pcfx',),
    'vb': ('mednafen_vb',),
    'vba-m': ('vbam',),
}

DEFAULTS_FILE      = DEFAULTS_DIR / 'configgen-defaults.yml'
HIPPOS_DEFAULTS    = HIPPOS_SHARE_DIR / 'hippos-defaults.conf'
HIPPOS_HW_DEFAULTS = Path('/run/hippos/hardware-defaults.conf')
HOTKEY_CONTEXT_DIR  = HIPPOS_SHARE_DIR / 'hotkeys' / 'contexts'
WHEEL_PROXY_BIN     = Path('/usr/lib/hippos/hippos-wheel-proxy')
ES_INPUT_FILES = (
    USER_ES_DIR / 'es_input.cfg',
    Path('/usr/share/emulationstation/es_input.cfg'),
)

BUILTIN_DEFAULTS: dict[str, dict[str, str]] = {
    'snes':         {'emulator': 'libretro', 'core': 'bsnes_mercury_balanced'},
    'gba':          {'emulator': 'libretro', 'core': 'mgba'},
    'megadrive':    {'emulator': 'libretro', 'core': 'genesis_plus_gx'},
    'gb':           {'emulator': 'libretro', 'core': 'gambatte'},
    'gbc':          {'emulator': 'libretro', 'core': 'gambatte'},
    'nes':          {'emulator': 'libretro', 'core': 'nestopia'},
    'n64':          {'emulator': 'libretro', 'core': 'mupen64plus_next'},
    'psx':          {'emulator': 'libretro', 'core': 'pcsx_rearmed'},
    'mastersystem': {'emulator': 'libretro', 'core': 'genesis_plus_gx'},
    'gamegear':     {'emulator': 'libretro', 'core': 'genesis_plus_gx'},
    'atari2600':    {'emulator': 'libretro', 'core': 'stella'},
    'neogeo':       {'emulator': 'libretro', 'core': 'fbneo'},
    'openbor':      {'emulator': 'openbor', 'core': 'openbor6412'},
    'xbox':         {'emulator': 'xemu', 'core': 'xemu'},
    'chihiro':      {'emulator': 'xemu', 'core': 'xemu'},
    'ps3':          {'emulator': 'rpcs3', 'core': 'rpcs3'},
}

MUPEN_VALID_N64_CONTROLLER_GUIDS = {
    "050000007e0500001920000001800000",
    "05000000c82d00006928000000010000",
    "030000007e0500001920000011810000",
    "05000000c82d00001930000001000000",
    "03000000c82d00001930000011010000",
}

MUPEN_VALID_N64_CONTROLLER_NAMES = {
    "N64 Controller",
    "Nintendo Co., Ltd. N64 Controller",
    "8BitDo N64 Modkit",
    "8BitDo 64 BT",
    "8BitDo 8BitDo 64 Bluetooth Controller",
}

DOLPHIN_GC_MAPPING: dict[str, str] = {
    'a': 'Buttons/A',
    'b': 'Buttons/B',
    'x': 'Buttons/X',
    'y': 'Buttons/Y',
    'start': 'Buttons/Start',
    'select': 'Buttons/Z',
    'pageup': '',
    'pagedown': '',
    'up': 'D-Pad/Up',
    'down': 'D-Pad/Down',
    'left': 'D-Pad/Left',
    'right': 'D-Pad/Right',
    'l2': 'Triggers/L',
    'r2': 'Triggers/R',
    'joystick1up': 'Main Stick/Up',
    'joystick1down': 'Main Stick/Down',
    'joystick1left': 'Main Stick/Left',
    'joystick1right': 'Main Stick/Right',
    'joystick2up': 'C-Stick/Up',
    'joystick2down': 'C-Stick/Down',
    'joystick2left': 'C-Stick/Left',
    'joystick2right': 'C-Stick/Right',
    'hotkey': 'Buttons/Hotkey',
}

DOLPHIN_WHEEL_MAPPING: dict[str, str] = {
    'select': 'Buttons/Z',
    'start': 'Buttons/Start',
    'up': 'D-Pad/Up',
    'down': 'D-Pad/Down',
    'left': 'D-Pad/Left',
    'right': 'D-Pad/Right',
    'a': 'Buttons/A',
    'b': 'Buttons/B',
    'x': 'Buttons/X',
    'y': 'Buttons/Y',
    'pageup': 'Triggers/L-Analog',
    'pagedown': 'Triggers/R-Analog',
    'r2': 'Main Stick/Up',
    'l2': 'Main Stick/Down',
    'joystick1left': 'Main Stick/Left',
    'joystick1right': 'Main Stick/Right',
}

MUPEN_DEFAULT_MAPPING: dict[str, str] = {
    'AnalogDeadzone': '0,0',
    'AnalogPeak': '32768,32768',
    'l3': 'Mempak switch',
    'r3': 'Rumblepak switch',
    'a': 'C Button R',
    'b': 'A Button',
    'x': 'C Button U',
    'y': 'B Button',
    'start': 'Start',
    'select': '',
    'pageup': 'L Trig',
    'pagedown': 'R Trig',
    'l2': 'Z Trig',
    'r2': '',
    'up': 'DPad U',
    'down': 'DPad D',
    'right': 'DPad R',
    'left': 'DPad L',
    'joystick1up': 'Y Axis',
    'joystick1down': 'Y Axis',
    'joystick1left': 'X Axis',
    'joystick1right': 'X Axis',
    'joystick2up': 'C Button U',
    'joystick2down': 'C Button D',
    'joystick2left': 'C Button L',
    'joystick2right': 'C Button R',
}

MUPEN_N64_MAPPING: dict[str, str] = {
    'AnalogDeadzone': '0,0',
    'AnalogPeak': '32768,32768',
    'l3': 'Mempak switch',
    'r3': 'Rumblepak switch',
    'a': 'B Button',
    'b': 'A Button',
    'x': 'C Button U',
    'y': 'C Button L',
    'start': 'Start',
    'select': 'Z Trig',
    'pageup': 'L Trig',
    'pagedown': 'R Trig',
    'l2': 'C Button D',
    'r2': 'C Button R',
    'up': 'DPad U',
    'down': 'DPad D',
    'right': 'DPad R',
    'left': 'DPad L',
    'joystick1up': 'Y Axis',
    'joystick1down': 'Y Axis',
    'joystick1left': 'X Axis',
    'joystick1right': 'X Axis',
    'joystick2up': '',
    'joystick2down': '',
    'joystick2left': '',
    'joystick2right': '',
}

LINDBERGH_TEMPLATE_DIR = Path('/usr/share/hippos/lindbergh')
LINDBERGH_TEMPLATE_INI = LINDBERGH_TEMPLATE_DIR / 'lindbergh.ini'
LINDBERGH_TEMPLATE_CONTROLS = LINDBERGH_TEMPLATE_DIR / 'controls.ini'
LINDBERGH_CONFIG_DIR = CONFIGS / 'lindbergh'
LINDBERGH_CONFIG_FILE = LINDBERGH_CONFIG_DIR / 'lindbergh.ini'
LINDBERGH_CONTROLS_FILE = LINDBERGH_CONFIG_DIR / 'controls.ini'
LINDBERGH_SAVES_DIR = SAVES / 'lindbergh'

LINDBERGH_PAD_MAPPING: dict[str, str] = {
    'a': 'BUTTON_2',
    'b': 'BUTTON_1',
    'x': 'BUTTON_4',
    'y': 'BUTTON_3',
    'start': 'BUTTON_START',
    'select': 'COIN',
    'up': 'BUTTON_UP',
    'down': 'BUTTON_DOWN',
    'left': 'BUTTON_LEFT',
    'right': 'BUTTON_RIGHT',
    'joystick1up': 'ANALOGUE_2',
    'joystick1left': 'ANALOGUE_1',
    'pageup': 'BUTTON_5',
    'pagedown': 'BUTTON_6',
    'l2': 'BUTTON_7',
    'r2': 'BUTTON_8',
    'l3': 'BUTTON_SERVICE',
}

LINDBERGH_WHEEL_MAPPING: dict[str, str] = {
    'a': 'BUTTON_2',
    'b': 'BUTTON_1',
    'x': 'BUTTON_4',
    'y': 'BUTTON_3',
    'start': 'BUTTON_START',
    'select': 'COIN',
    'left': 'BUTTON_LEFT',
    'right': 'BUTTON_RIGHT',
    'joystick1left': 'ANALOGUE_1',
    'pageup': 'BUTTON_DOWN',
    'pagedown': 'BUTTON_UP',
    'l2': 'ANALOGUE_3',
    'r2': 'ANALOGUE_2',
    'l3': 'BUTTON_SERVICE',
}

LINDBERGH_GUN_MAPPING: dict[str, str] = {
    'a': 'BUTTON_2',
    'b': 'BUTTON_1',
    'x': 'BUTTON_4',
    'y': 'BUTTON_3',
    'start': 'BUTTON_START',
    'select': 'COIN',
    'up': 'BUTTON_UP',
    'down': 'BUTTON_DOWN',
    'left': 'BUTTON_LEFT',
    'right': 'BUTTON_RIGHT',
    'joystick1up': 'ANALOGUE_2',
    'joystick1left': 'ANALOGUE_1',
    'pageup': 'BUTTON_5',
    'pagedown': 'BUTTON_6',
    'l2': 'BUTTON_7',
    'r2': 'BUTTON_8',
    'l3': 'BUTTON_SERVICE',
}

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='[emulatorlauncher] %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)],
)
_log = logging.getLogger('emulatorlauncher')

# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class ControllerInfo:
    player:      int
    index:       int  = 0
    guid:        str  = ''
    name:        str  = ''
    device_path: str  = ''
    is_wheel:    bool = False
    wheel_rotation_angle: int = 0
    nb_buttons:  int  = 0
    nb_hats:     int  = 0
    nb_axes:     int  = 0


@dataclass
class LaunchContext:
    system:      str
    rom:         Path
    emulator:    str
    core:        str
    gameinfoxml:  Optional[Path] = None
    lightgun:    bool = False
    wheel:       bool = False
    controllers: list[ControllerInfo] = field(default_factory=list)
    game_wheel:    dict[str, str] = field(default_factory=dict)
    game_gun:      dict[str, str] = field(default_factory=dict)
    resolution:    Optional[tuple[int, int]] = None
    bezel:         Optional[Path] = None
    netplay_mode:  str = ''   # 'host' | 'client' | 'spectator' | ''
    netplay_ip:    str = ''
    netplay_port:  str = ''


@dataclass(frozen=True)
class ESBinding:
    name: str
    type: str
    code: int
    value: int


@dataclass
class ESControllerProfile:
    device_name: str
    device_guid: str
    device_path: str
    inputs: dict[str, ESBinding]


# ── Settings / defaults ────────────────────────────────────────────────────────

def _load_hippos_conf() -> dict[str, str]:
    return _read_conf_file(HIPPOS_CONF)


def _read_conf_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, _, v = line.partition('=')
                result[k.strip()] = v.strip()
    except OSError as exc:
        _log.warning("Could not read %s: %s", path, exc)
    return result


def _load_effective_hippos_conf() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in (HIPPOS_DEFAULTS, HIPPOS_HW_DEFAULTS, HIPPOS_CONF):
        result.update(_read_conf_file(path))
    return result


def _load_yaml_defaults() -> dict:
    if not _HAS_YAML or not DEFAULTS_FILE.exists():
        return {}
    try:
        data = yaml.safe_load(DEFAULTS_FILE.read_text())
        return data or {}
    except Exception as exc:
        _log.warning("Could not load %s: %s", DEFAULTS_FILE, exc)
        return {}


def _get_yaml_system_options(system: str) -> dict:
    """Return the options block from configgen-defaults.yml for a system."""
    entry = _load_yaml_defaults().get(system)
    if not entry:
        return {}
    return entry.get('options') or {}


def _apply_yaml_options(conf: dict[str, str], system: str) -> None:
    """Inject YAML system options into conf as {system}.KEY (user conf wins)."""
    for key, value in _get_yaml_system_options(system).items():
        if key == 'forceNoBezel':
            conf_key = f'{system}.bezel'
            conf_val = 'none' if value else ''
        elif isinstance(value, bool):
            conf_key = f'{system}.{key}'
            conf_val = 'true' if value else 'false'
        else:
            conf_key = f'{system}.{key}'
            conf_val = str(value)
        if conf_key not in conf:
            conf[conf_key] = conf_val


def _hud_supported(system: str) -> bool:
    """False if YAML marks this system as hud_support: false."""
    return _get_yaml_system_options(system).get('hud_support', True) is not False


def _load_game_wheel_metadata(gameinfoxml: Optional[Path]) -> dict[str, str]:
    if gameinfoxml is None or not gameinfoxml.exists():
        return {}
    try:
        root = ET.parse(gameinfoxml).getroot()
    except ET.ParseError as exc:
        _log.warning("Could not parse %s: %s", gameinfoxml, exc)
        return {}
    wheel = root.find('.//wheel')
    if wheel is None:
        return {}
    data = {k: v for k, v in wheel.attrib.items() if v}
    if 'wheel' not in data:
        data['wheel'] = 'joystick1left'
    return data


def _load_game_gun_metadata(gameinfoxml: Optional[Path]) -> dict[str, str]:
    if gameinfoxml is None or not gameinfoxml.exists():
        return {}
    try:
        root = ET.parse(gameinfoxml).getroot()
    except ET.ParseError as exc:
        _log.warning("Could not parse %s: %s", gameinfoxml, exc)
        return {}

    gun = root.find('.//gun')
    if gun is None:
        return {}
    data = {k: v for k, v in gun.attrib.items() if v}
    if 'type' not in data and 'gun_type' in data:
        data['type'] = data['gun_type']
    return data


def configure_emulator(rom: Path) -> bool:
    return str(rom) == 'config'


def generate_sdl_game_controller_config(controllers: list[ControllerInfo], ignore_buttons: Optional[list[str]] = None) -> str:
    ignored = {name.strip().lower() for name in (ignore_buttons or [])}
    profiles = _load_es_input_configs()
    lines: list[str] = []
    seen_guids: set[str] = set()

    for ctrl in controllers:
        guid = ctrl.guid.strip()
        if not guid or guid == '-1' or _normalize(guid) in seen_guids:
            continue
        profile = _pick_es_profile(profiles, ctrl)
        if profile is None:
            continue

        mapping = _sdl_controller_mapping(profile, ignored)
        if not mapping:
            continue

        seen_guids.add(_normalize(guid))
        name = (ctrl.name or profile.device_name or 'HippOS Controller').replace(',', ' ').strip()
        fields = [guid, name, 'platform:Linux']
        fields.extend(f'{key}:{value}' for key, value in mapping)
        lines.append(','.join(fields) + ',')

    return '\n'.join(lines)


def _sdl_binding_value(binding: ESBinding, positive: Optional[bool] = None) -> Optional[str]:
    if binding.type == 'button':
        return f'b{binding.code}'
    if binding.type == 'hat':
        return f'h{binding.code}.{abs(binding.value)}'
    if binding.type == 'axis':
        prefix = ''
        if positive is True:
            prefix = '+'
        elif positive is False:
            prefix = '-'
        return f'{prefix}a{binding.code}'
    return None


def _sdl_controller_mapping(
    profile: ESControllerProfile,
    ignored: set[str],
) -> list[tuple[str, str]]:
    button_map = [
        ('a', 'a'),
        ('b', 'b'),
        ('x', 'x'),
        ('y', 'y'),
        ('back', 'select'),
        ('start', 'start'),
        ('leftshoulder', 'pageup'),
        ('rightshoulder', 'pagedown'),
        ('lefttrigger', 'l2'),
        ('righttrigger', 'r2'),
        ('leftstick', 'l3'),
        ('rightstick', 'r3'),
    ]
    axis_map = [
        ('leftx', 'joystick1left'),
        ('lefty', 'joystick1up'),
        ('rightx', 'joystick2left'),
        ('righty', 'joystick2up'),
    ]
    dpad_map = [
        ('dpup', 'up'),
        ('dpdown', 'down'),
        ('dpleft', 'left'),
        ('dpright', 'right'),
    ]

    mapping: list[tuple[str, str]] = []
    for sdl_name, es_name in button_map:
        if es_name in ignored:
            continue
        binding = profile.inputs.get(es_name)
        if binding is None:
            continue
        value = _sdl_binding_value(binding)
        if value is not None:
            mapping.append((sdl_name, value))

    for sdl_name, es_name in axis_map:
        if es_name in ignored:
            continue
        binding = profile.inputs.get(es_name)
        if binding is None:
            continue
        positive = None
        if binding.type == 'axis' and binding.value:
            positive = binding.value > 0
        value = _sdl_binding_value(binding, positive)
        if value is not None:
            mapping.append((sdl_name, value))

    for sdl_name, es_name in dpad_map:
        if es_name in ignored:
            continue
        binding = profile.inputs.get(es_name)
        if binding is None:
            continue
        positive = None
        if binding.type == 'axis' and binding.value:
            positive = binding.value > 0
        value = _sdl_binding_value(binding, positive)
        if value is not None:
            mapping.append((sdl_name, value))

    return mapping


def _gun_type(ctx: LaunchContext) -> str:
    gun_type = ctx.game_gun.get('type', '').strip().lower()
    if gun_type in ('justifier', 'guncon'):
        return gun_type
    return 'guncon'


def _normalize(value: str) -> str:
    return ''.join(ch for ch in value.strip().casefold() if ch.isalnum())


def _load_es_input_configs() -> list[ESControllerProfile]:
    es_path = next((path for path in ES_INPUT_FILES if path.exists()), None)
    if es_path is None:
        return []
    try:
        root = ET.parse(es_path).getroot()
    except ET.ParseError as exc:
        _log.warning("Could not parse %s: %s", es_path, exc)
        return []

    configs: list[ESControllerProfile] = []
    for node in root.findall('inputConfig'):
        if node.attrib.get('type') != 'joystick':
            continue
        inputs: dict[str, ESBinding] = {}
        for input_node in node.findall('input'):
            name = (input_node.attrib.get('name') or '').strip().lower()
            type_name = (input_node.attrib.get('type') or '').strip().lower()
            code_text = input_node.attrib.get('id') or input_node.attrib.get('code')
            value_text = input_node.attrib.get('value', '0')
            if not name or not type_name or code_text is None:
                continue
            try:
                code = int(code_text)
                value = int(value_text)
            except ValueError:
                continue
            inputs[name] = ESBinding(name=name, type=type_name, code=code, value=value)
        configs.append(
            ESControllerProfile(
                device_name=node.attrib.get('deviceName', ''),
                device_guid=node.attrib.get('deviceGUID', ''),
                device_path=node.attrib.get('devicePath', ''),
                inputs=inputs,
            )
        )
    return configs


def _pick_es_profile(
    profiles: list[ESControllerProfile],
    ctrl: ControllerInfo,
) -> Optional[ESControllerProfile]:
    normalized_name = _normalize(ctrl.name)
    normalized_guid = _normalize(ctrl.guid)
    normalized_path = _normalize(ctrl.device_path)

    for profile in profiles:
        if _normalize(profile.device_guid) == normalized_guid and _normalize(profile.device_name) == normalized_name:
            return profile
    for profile in profiles:
        if _normalize(profile.device_guid) == normalized_guid:
            return profile
    for profile in profiles:
        if _normalize(profile.device_path) == normalized_path and normalized_path:
            return profile
    for profile in profiles:
        if _normalize(profile.device_name) == normalized_name:
            return profile
    return profiles[0] if profiles else None


def _conf_value(conf: dict[str, str], key: str, default: str = '') -> str:
    value = conf.get(key, default)
    if value is None:
        return default
    value = str(value).strip()
    if not value or value.lower() == 'auto':
        return default
    return value


def _conf_int(conf: dict[str, str], key: str, default: int = 0) -> int:
    value = _conf_value(conf, key, '')
    if not value:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _conf_bool(conf: dict[str, str], key: str, default: bool = False) -> bool:
    value = _conf_value(conf, key, '')
    if not value:
        return default
    return value.lower() in ('1', 'true', 'on', 'enabled', 'yes')


def _new_ini_parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # keep case-sensitive option names
    return parser


def _ensure_section(parser: configparser.ConfigParser, section: str) -> None:
    if not parser.has_section(section):
        parser.add_section(section)


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Path):
        return json.dumps(str(value))
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_toml_value(item) for item in value) + ']'
    raise TypeError(f'Unsupported TOML value type: {type(value)!r}')


def _toml_write_table(fh, table: dict[str, object], prefix: tuple[str, ...] = ()) -> None:
    scalars: list[tuple[str, object]] = []
    nested: list[tuple[str, dict[str, object]]] = []
    for key, value in table.items():
        if isinstance(value, dict):
            nested.append((key, value))
        else:
            scalars.append((key, value))

    if prefix:
        fh.write(f"[{'.'.join(prefix)}]\n")

    for key, value in scalars:
        fh.write(f"{key} = {_toml_value(value)}\n")

    for idx, (key, value) in enumerate(nested):
        if scalars or idx > 0:
            fh.write('\n')
        _toml_write_table(fh, value, prefix + (key,))


def _write_toml(path: Path, config: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fh:
        _toml_write_table(fh, config)


def _read_toml(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        with path.open('rb') as fh:
            return tomllib.load(fh)
    except Exception as exc:
        _log.warning("Could not read %s: %s", path, exc)
        return {}


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for item in value.split('.'):
        try:
            parts.append(int(item))
        except ValueError:
            break
    return tuple(parts)


def _probe_vulkan_version() -> Optional[tuple[int, ...]]:
    vulkaninfo = which('vulkaninfo')
    if vulkaninfo is None:
        return None
    try:
        proc = subprocess.run([vulkaninfo, '--summary'], capture_output=True, text=True, timeout=5, check=False)
    except Exception:
        return None
    output = '\n'.join(part for part in (proc.stdout, proc.stderr) if part)
    for pattern in (
        r'Vulkan Instance Version:\s*([0-9]+(?:\.[0-9]+){1,2})',
        r'Vulkan API Version:\s*([0-9]+(?:\.[0-9]+){1,2})',
        r'Vulkan Version:\s*([0-9]+(?:\.[0-9]+){1,2})',
    ):
        match = re.search(pattern, output)
        if match:
            return _version_tuple(match.group(1))
    return None


def _find_executable(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    preferred_names = (
        'lindbergh-loader',
        'lindbergh-loader.exe',
        'shadps4',
        'shadps4.exe',
        'model2emu',
        'model2emu.exe',
    )
    for name in preferred_names:
        candidate = root / name
        if candidate.exists() and candidate.is_file():
            return candidate
        candidate = root / 'bin' / name
        if candidate.exists() and candidate.is_file():
            return candidate
    for candidate in root.rglob('*'):
        if candidate.is_file():
            try:
                mode = candidate.stat().st_mode
            except OSError:
                continue
            if mode & 0o111:
                return candidate
    return None


def _display_resolution_from_conf(conf: dict[str, str]) -> Optional[tuple[int, int]]:
    value = _conf_value(conf, 'display.resolution', '')
    if not value or value == 'preferred':
        return None
    match = re.match(r'(?P<w>\d+)x(?P<h>\d+)', value)
    if not match:
        return None
    return int(match.group('w')), int(match.group('h'))


def _ensure_section(parser: configparser.ConfigParser, section: str) -> None:
    if not parser.has_section(section):
        parser.add_section(section)


def _resolve_mergerfs_path(path: Path) -> Path:
    """Resolve a path that sits under a mergerfs mount to its real branch path.

    mergerfs presents a unified view across multiple branches. Some emulators
    need the actual physical path (e.g. to resolve symlinks or use inotify).
    Reads /proc/mounts, finds the matching fuse.mergerfs entry, then walks the
    colon-separated branch list until it finds one where the path exists.
    """
    try:
        path_str = str(path)
        with open('/proc/mounts') as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3 or parts[2] != 'fuse.mergerfs':
                    continue
                mount_point = parts[1]
                if not (path_str.startswith(mount_point + '/') or path_str == mount_point):
                    continue
                relative = path_str[len(mount_point):]
                for branch in parts[0].split(':'):
                    branch = branch.strip()
                    if not branch:
                        continue
                    if not branch.startswith('/'):
                        branch = '/' + branch
                    candidate = Path(branch.rstrip('/') + relative)
                    if candidate.exists():
                        _log.debug("mergerfs: resolved %s -> %s", path, candidate)
                        return candidate
    except Exception as exc:
        _log.debug("mergerfs path resolution failed: %s", exc)
    return path


def _lindbergh_short_rom_name(rom: Path) -> str:
    return rom.stem.lower()


def _lindbergh_game_section(short_rom: str) -> str:
    if short_rom.startswith(('outr', 'hummer', 'hdkotr', 'harley', 'rtuned', 'initiad', 'segartv')):
        return 'Driving'
    if short_rom.startswith(('ghostsev', 'hotd4', 'hotdex', 'hotd4sp', 'primevah', 'primehunt', '2spicy', 'letsgoju', 'letsgojua')):
        return 'Shooting'
    if short_rom.startswith('abcli'):
        return 'ABC'
    if short_rom.startswith(('mj4', 'axa')):
        return 'Mahjong'
    return 'Digital'


def _lindbergh_mapping_for_device(short_rom: str, device_type: str, is_real_wheel: bool) -> dict[str, str]:
    if device_type == 'gun':
        return dict(LINDBERGH_GUN_MAPPING)

    if device_type == 'wheel':
        mapping = dict(LINDBERGH_WHEEL_MAPPING)
        if not is_real_wheel:
            x = mapping.pop('x', None)
            y = mapping.pop('y', None)
            pageup = mapping.pop('pageup', None)
            pagedown = mapping.pop('pagedown', None)
            if x is not None:
                mapping['pageup'] = x
            if y is not None:
                mapping['b'] = y
            if pagedown is not None:
                mapping['x'] = pagedown
            if pageup is not None:
                mapping['y'] = pageup

        if short_rom in ('hdkotr',) or 'harley' in short_rom:
            mapping['x'] = 'BUTTON_2'
            mapping['l2'] = 'ANALOGUE_4'
            mapping['r2'] = 'ANALOGUE_1'
            mapping['joystick1left'] = 'ANALOGUE_2'
            mapping.pop('a', None)
            mapping.pop('y', None)
            mapping['pageup'] = 'BUTTON_4'
            mapping['pagedown'] = 'BUTTON_3'
        if short_rom == 'rtuned':
            mapping['x'] = 'BUTTON_DOWN'
            mapping['a'] = 'BUTTON_RIGHT'
            mapping['y'] = 'BUTTON_1_ON_PLAYER_2'
            mapping.pop('right', None)
        if short_rom.startswith('initiad'):
            mapping['x'] = 'BUTTON_1'
            mapping['up'] = 'BUTTON_UP'
            mapping['down'] = 'BUTTON_DOWN'
            mapping.pop('b', None)
        if short_rom.startswith('hummer'):
            mapping['a'] = 'BUTTON_DOWN_ON_PLAYER_2'
            mapping['x'] = 'BUTTON_DOWN'
            mapping.pop('pageup', None)
        if short_rom.startswith('segartv'):
            mapping['a'] = 'BUTTON_1_ON_PLAYER_2'
            mapping['x'] = 'BUTTON_DOWN'
            mapping.pop('pageup', None)
        if short_rom.startswith('outr'):
            mapping['x'] = 'BUTTON_DOWN'
        if short_rom in ('rtuned',) or short_rom.startswith(('segartv', 'outr', 'initiad')):
            mapping['pageup'] = 'BUTTON_DOWN_ON_PLAYER_2'
            mapping['pagedown'] = 'BUTTON_UP_ON_PLAYER_2'
        return mapping

    mapping = dict(LINDBERGH_PAD_MAPPING)
    if short_rom.startswith('outr'):
        mapping['x'] = 'BUTTON_DOWN'
        mapping['pageup'] = 'BUTTON_DOWN_ON_PLAYER_2'
        mapping['pagedown'] = 'BUTTON_UP_ON_PLAYER_2'
        mapping.pop('joystick1up', None)
        mapping.pop('down', None)
    if short_rom.startswith('hummer'):
        mapping['a'] = 'BUTTON_DOWN_ON_PLAYER_2'
        mapping['pageup'] = 'BUTTON_5'
        mapping['pagedown'] = 'BUTTON_6'
        mapping.pop('joystick1up', None)
        mapping.pop('down', None)
    if short_rom.startswith('initiad'):
        mapping['x'] = 'BUTTON_1'
        mapping.pop('joystick1up', None)
        mapping.pop('b', None)
    if short_rom == 'rtuned':
        mapping['a'] = 'BUTTON_RIGHT'
        mapping['y'] = 'BUTTON_1_ON_PLAYER_2'
        mapping.pop('joystick1up', None)
        mapping.pop('right', None)
        mapping.pop('down', None)
    if short_rom.startswith('segartv'):
        mapping['a'] = 'BUTTON_1_ON_PLAYER_2'
        mapping.pop('joystick1up', None)
        mapping.pop('down', None)
    if short_rom in ('hdkotr',) or 'harley' in short_rom:
        mapping['joystick1left'] = 'ANALOGUE_2'
        mapping['r2'] = 'ANALOGUE_1'
        mapping['l2'] = 'ANALOGUE_4'
        mapping['x'] = 'BUTTON_2'
        mapping['pageup'] = 'BUTTON_4'
        mapping['pagedown'] = 'BUTTON_3'
        mapping.pop('joystick1up', None)
        mapping.pop('a', None)
        mapping.pop('y', None)
    if short_rom.startswith('abcli'):
        mapping['a'] = 'BUTTON_1'
        mapping['b'] = 'BUTTON_2'
        mapping['x'] = 'BUTTON_3'
        mapping['r2'] = 'ANALOGUE_3'
        mapping.pop('l2', None)
        mapping.pop('y', None)
    return mapping


def _lindbergh_binding_to_value(binding: ESBinding, ctrl: ESControllerProfile, logical_name: str) -> Optional[str]:
    prefix = ctrl.device_path
    if not prefix:
        return None
    if binding.type in ('button', 'key'):
        return f'{prefix}:KEY:{binding.code}'
    if binding.type == 'axis':
        axis = 'ABS_NEG' if binding.value < 0 else 'ABS'
        return f'{prefix}:{axis}:{binding.code}'
    if binding.type == 'hat':
        axis_base = 16 + int(binding.code) * 2
        if binding.value in (1, 4):
            axis_base += 1
        return f'{prefix}:ABS:{axis_base}'
    return None


def _lindbergh_apply_mapping(
    parser: configparser.ConfigParser,
    section: str,
    mapping: dict[str, str],
    profile: ESControllerProfile,
    ctrl: ControllerInfo,
    player_index: int,
) -> None:
    _ensure_section(parser, section)
    for logical_name, button_name in mapping.items():
        source_name = logical_name
        if source_name not in profile.inputs:
            if logical_name == 'joystick1right' and 'joystick1left' in profile.inputs:
                source_name = 'joystick1left'
            elif logical_name == 'joystick1down' and 'joystick1up' in profile.inputs:
                source_name = 'joystick1up'
            elif logical_name == 'joystick2right' and 'joystick2left' in profile.inputs:
                source_name = 'joystick2left'
            elif logical_name == 'joystick2down' and 'joystick2up' in profile.inputs:
                source_name = 'joystick2up'
        binding = profile.inputs.get(source_name)
        if binding is None:
            continue

        value = _lindbergh_binding_to_value(binding, profile, logical_name)
        if value is None:
            continue

        target = button_name
        player_for_target = player_index
        if target.endswith('_ON_PLAYER_2'):
            target = target[:-12]
            player_for_target = 2
        if target == 'COIN' and player_index > 1:
            continue

        if target.startswith('ANALOGUE_'):
            if player_index == 1:
                parser.set(section, target, value)
            continue
        if target in {'TEST_BUTTON', 'PLAYER_1_BUTTON_SERVICE'}:
            parser.set(section, target, value)
            continue
        parser.set(section, f'PLAYER_{player_for_target}_{target}', value)


def _lindbergh_write_templates() -> tuple[configparser.ConfigParser, configparser.ConfigParser]:
    ini = _new_ini_parser()
    ini.optionxform = str
    ini.read(LINDBERGH_TEMPLATE_INI)
    controls = _new_ini_parser()
    controls.optionxform = str
    controls.read(LINDBERGH_TEMPLATE_CONTROLS)
    return ini, controls


def _write_dolphin_controller_configs(ctx: LaunchContext, profiles: list[ESControllerProfile]) -> None:
    if ctx.system not in ('gamecube', 'triforce'):
        return

    config_path = DOLPHIN_CONFIG_DIR / 'GCPadNew.ini'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    profile_counts: dict[str, int] = {}
    with config_path.open('w', encoding='utf-8') as fh:
        for ctrl in ctx.controllers:
            profile = _pick_es_profile(profiles, ctrl)
            name_key = _normalize(ctrl.name)
            nsamepad = profile_counts.get(name_key, 0)
            profile_counts[name_key] = nsamepad + 1
            if profile is None:
                _log.warning("No ES input profile matched controller %s (%s)", ctrl.name, ctrl.guid)
                continue

            mapping = DOLPHIN_WHEEL_MAPPING if ctrl.is_wheel and ctx.system in ('gamecube', 'triforce') else DOLPHIN_GC_MAPPING
            section = f'GCPad{ctrl.player}'
            fh.write(f'[{section}]\n')
            fh.write(f'Device = evdev/{nsamepad}/{ctrl.name}\n')
            if ctrl.is_wheel and ctx.system in ('gamecube', 'triforce'):
                fh.write('Rumble/Motor = Constant\n')
                fh.write('Rumble/Motor/Range = -100.\n')
                fh.write('Main Stick/Dead Zone = 0.\n')

            for logical_name, target in mapping.items():
                if not target:
                    continue
                binding = profile.inputs.get(logical_name)
                if binding is None:
                    continue
                value = _es_binding_to_dolphin(binding, target, ctrl, profile)
                if value is None:
                    continue
                fh.write(f'{target} = {value}\n')
            fh.write('\n')


def _mupen_selected_mapping(ctrl: ControllerInfo) -> dict[str, str]:
    if ctrl.guid in MUPEN_VALID_N64_CONTROLLER_GUIDS or ctrl.name in MUPEN_VALID_N64_CONTROLLER_NAMES:
        return MUPEN_N64_MAPPING
    return MUPEN_DEFAULT_MAPPING


def _mupen_analog_peak(conf: dict[str, str], key: str) -> str:
    default_value = 32768
    multiplier = 1.0
    try:
        multiplier = float(_conf_value(conf, key, '1') or '1')
    except ValueError:
        multiplier = 1.0
    adjusted = round(default_value * multiplier)
    return f'{adjusted},{adjusted}'


def _mupen_analog_deadzone(conf: dict[str, str], key: str, default_peak: str) -> str:
    default_value = int(default_peak.split(',')[0])
    try:
        deadzone_multiplier = float(_conf_value(conf, key, '0.01') or '0.01')
    except ValueError:
        deadzone_multiplier = 0.01
    deadzone = round(default_value * deadzone_multiplier)
    return f'{deadzone},{deadzone}'


def _write_mupen_controller_configs(ctx: LaunchContext, profiles: list[ESControllerProfile], parser: configparser.ConfigParser, conf: dict[str, str]) -> None:
    for ctrl in ctx.controllers:
        profile = _pick_es_profile(profiles, ctrl)
        if profile is None:
            _log.warning("No ES input profile matched controller %s (%s)", ctrl.name, ctrl.guid)
            continue
        mapping = _mupen_selected_mapping(ctrl)
        section = f'Input-SDL-Control{ctrl.player}'
        _ensure_section(parser, section)
        parser.set(section, 'Version', '2')
        parser.set(section, 'mode', '0')
        parser.set(section, 'device', str(ctrl.index))
        parser.set(section, 'name', str(ctrl.name.encode('ascii', 'ignore')))
        parser.set(section, 'plugged', 'True')
        parser.set(section, 'plugin', '2')
        parser.set(section, 'mouse', 'False')

        peak = _mupen_analog_peak(conf, f'mupen64-sensitivity{ctrl.player}')
        parser.set(section, 'AnalogPeak', peak)
        if ctrl.is_wheel and ctx.system in ('n64', 'n64dd'):
            parser.set(section, 'AnalogDeadzone', '0,0')
        else:
            parser.set(section, 'AnalogDeadzone', _mupen_analog_deadzone(conf, f'mupen64-deadzone{ctrl.player}', peak))

        for logical_name, target in mapping.items():
            if target in {'AnalogDeadzone', 'AnalogPeak'}:
                continue
            binding = profile.inputs.get(logical_name)
            if binding is None:
                continue
            value = _es_binding_to_mupen(binding, target, ctrl, profile)
            if value is None or target == '':
                continue
            parser.set(section, target, value)

    for x in range(len(ctx.controllers) + 1, 4):
        section = f'Input-SDL-Control{x}'
        if parser.has_section(section):
            parser.remove_section(section)


def _es_binding_to_dolphin(binding: ESBinding, target: str, ctrl: ControllerInfo, profile: ESControllerProfile) -> Optional[str]:
    if binding.type == 'button':
        return f'`Button {binding.code}`'

    if binding.type == 'hat':
        hat_base = ctrl.nb_axes + binding.code * 2
        if binding.value in (1, 4):
            return f'`Axis {hat_base + 1}{"-" if binding.value == 1 else "+"}`'
        return f'`Axis {hat_base}{"-" if binding.value == 8 else "+"}`'

    if binding.type == 'axis':
        prefix = 'Full ' if target in {'Triggers/L-Analog', 'Triggers/R-Analog'} else ''
        if binding.value < 0:
            return f'`{prefix}Axis {binding.code}-`'
        return f'`{prefix}Axis {binding.code}+`'

    if binding.type == 'key':
        return f'`Button {binding.code}`'

    return None


def _es_binding_to_mupen(binding: ESBinding, target: str, ctrl: ControllerInfo, profile: ESControllerProfile) -> Optional[str]:
    if binding.type == 'button':
        if target in {'X Axis', 'Y Axis'}:
            reverse_map = {
                'up': 'down',
                'left': 'right',
                'joystick1up': 'joystick1down',
                'joystick1left': 'joystick1right',
                'joystick2up': 'joystick2down',
                'joystick2left': 'joystick2right',
            }
            if binding.name in ('down', 'right', 'joystick1down', 'joystick1right', 'joystick2down', 'joystick2right'):
                return None
            reverse_name = reverse_map.get(binding.name)
            if reverse_name and reverse_name in profile.inputs:
                reverse_binding = profile.inputs[reverse_name]
                return f'button({binding.code}, {reverse_binding.code})'
        return f'button({binding.code})'
    if binding.type == 'hat':
        if target in {'X Axis', 'Y Axis'}:
            if binding.value == 1:
                return f'hat({binding.code} Up Down)'
            if binding.value == 4:
                return f'hat({binding.code} Down Up)'
            if binding.value == 2:
                return f'hat({binding.code} Right Left)'
            if binding.value == 8:
                return f'hat({binding.code} Left Right)'
            return None
        direction = {1: 'Up', 2: 'Right', 4: 'Down', 8: 'Left'}.get(binding.value)
        if direction:
            return f'hat({binding.code} {direction})'
        return None
    if binding.type == 'axis':
        if target in {'X Axis', 'Y Axis'}:
            if binding.value < 0:
                return f'axis({binding.code}-,{binding.code}+)'
            return f'axis({binding.code}+,{binding.code}-)'
        if binding.value > 0:
            return f'axis({binding.code}+)'
        return f'axis({binding.code}-)'
    if binding.type == 'key':
        return f'button({binding.code})'
    return None


def _ratio_index(conf: dict[str, str]) -> int:
    ratio = _conf_value(conf, 'global.ratio', 'core')
    if ratio in LIBRETRO_RATIO_INDEXES:
        return LIBRETRO_RATIO_INDEXES.index(ratio)
    return LIBRETRO_RATIO_INDEXES.index('core')


def resolve_emulator_core(
    system: str,
    forced_emulator: Optional[str],
    forced_core: Optional[str],
    rom: Optional[Path] = None,
) -> tuple[str, str]:
    conf = _load_hippos_conf()

    global_em  = conf.get('global.emulator') or None
    global_co  = conf.get('global.core')     or None

    user_em    = conf.get(f'{system}.emulator') or None
    user_co    = conf.get(f'{system}.core')     or None

    folder_em = folder_co = None
    game_em   = game_co   = None
    if rom is not None:
        gsname    = rom.name.replace('=', '').replace('#', '')
        folder_em = conf.get(f'{system}.folder["{rom.parent}"].emulator') or None
        folder_co = conf.get(f'{system}.folder["{rom.parent}"].core')     or None
        game_em   = conf.get(f'{system}["{gsname}"].emulator') or None
        game_co   = conf.get(f'{system}["{gsname}"].core')     or None

    defaults = _load_yaml_defaults()
    sys_def  = defaults.get(system) or BUILTIN_DEFAULTS.get(system) or {}

    # Resolution order: CLI > game > folder > system > global > defaults
    emulator = forced_emulator or game_em or folder_em or user_em or global_em or sys_def.get('emulator') or 'libretro'
    core     = forced_core     or game_co or folder_co or user_co or global_co or sys_def.get('core')     or ''
    return emulator, core


# ── Emulator binary lookup ─────────────────────────────────────────────────────

def _find_emulator_bin(*names: str) -> Optional[Path]:
    """Find an installed standalone emulator binary.

    Search order matches the runtime resolution policy:
    1. /userdata/emulators/<package>/current/  (user-updated)
    2. /opt/emulators/<package>/                      (OS-bundled artifact)
    """
    for name in names:
        packages = (name,) + ARTIFACT_PACKAGE_ALIASES.get(name, ())
        binaries = STANDALONE_BINARIES.get(name, (name,))
        search_dirs = [
            *(USERDATA / 'emulators' / package / 'current' for package in packages),
            *(Path('/opt/emulators') / package for package in packages),
            *(USERDATA / 'emulators' / package for package in packages),
        ]
        for d in search_dirs:
            for binary in binaries:
                for candidate in (d / binary, d / 'bin' / binary):
                    if candidate.exists() and os.access(str(candidate), os.X_OK):
                        return candidate
        for binary in binaries:
            found = which(binary)
            if found:
                return Path(found)
            for system_dir in (Path('/usr/bin'), Path('/usr/games'), Path('/usr/local/bin')):
                candidate = system_dir / binary
                if candidate.exists() and os.access(str(candidate), os.X_OK):
                    return candidate
    return None


def _find_emulator_bin_in_package(package: str, *binary_names: str) -> Optional[Path]:
    """Find a binary inside a specific emulator package directory."""
    search_dirs = [
        USERDATA / 'emulators' / package / 'current',
        Path('/opt/emulators') / package,
    ]
    for d in search_dirs:
        for binary in binary_names:
            for candidate in (d / binary, d / 'bin' / binary):
                if candidate.exists() and os.access(str(candidate), os.X_OK):
                    return candidate
    for binary in binary_names:
        found = which(binary)
        if found:
            return Path(found)
        for system_dir in (Path('/usr/bin'), Path('/usr/games'), Path('/usr/local/bin')):
            candidate = system_dir / binary
            if candidate.exists() and os.access(str(candidate), os.X_OK):
                return candidate
    return None


def _core_search_paths() -> list[Path]:
    paths = list(CORE_SEARCH_PATHS[:2])
    paths.extend(
        path
        for path in sorted(Path('/opt/emulators').glob('*/cores'))
        if path not in paths
    )
    paths.extend(CORE_SEARCH_PATHS[2:])
    return paths


def find_core(core_name: str) -> Optional[Path]:
    for candidate_core in (core_name, *LIBRETRO_CORE_ALIASES.get(core_name, ())):
        filename = f'{candidate_core}_libretro.so'
        for search_dir in _core_search_paths():
            candidate = search_dir / filename
            if candidate.exists():
                if candidate_core != core_name:
                    _log.info("Resolved libretro core alias %s -> %s", core_name, candidate_core)
                return candidate
    return None


# ── Hotkey context ─────────────────────────────────────────────────────────────

HOTKEYS_BIN = Path('/usr/lib/hippos/hippos-hotkeys')

@contextmanager
def hotkey_context(name: str):
    source = HOTKEY_CONTEXT_DIR / f'{name}.json'
    try:
        if source.exists():
            subprocess.run(
                [str(HOTKEYS_BIN), '--new-context', name, source.read_text()],
                capture_output=True,
            )
    except Exception as exc:
        _log.warning("Could not set hotkey context '%s': %s", name, exc)

    try:
        yield
    finally:
        try:
            subprocess.run(
                [str(HOTKEYS_BIN), '--default-context'],
                capture_output=True,
            )
        except Exception as exc:
            _log.warning("Could not reset hotkey context: %s", exc)


def _wheel_proxy_command(ctrl: ControllerInfo, ctx: LaunchContext, env: dict[str, str]) -> list[str]:
    wheel_meta = ctx.game_wheel or {}
    return [
        str(WHEEL_PROXY_BIN),
        '--device-path', ctrl.device_path,
        '--device-guid', ctrl.guid,
        '--device-name', ctrl.name,
        '--device-index', str(ctrl.index),
        '--proxy-name', f'HippOS wheel proxy P{ctrl.player}',
        '--wheel-name', wheel_meta.get('wheel', 'joystick1left'),
        '--accelerate-name', wheel_meta.get('accelerate', 'r2'),
        '--brake-name', wheel_meta.get('brake', 'l2'),
        '--downshift-name', wheel_meta.get('downshift', 'pageup'),
        '--upshift-name', wheel_meta.get('upshift', 'pagedown'),
        '--physical-rotation-angle', str(ctrl.wheel_rotation_angle or 900),
        '--rotation', env.get('HIPPOS_WHEEL_ROTATION', ''),
        '--deadzone', env.get('HIPPOS_WHEEL_DEADZONE', ''),
        '--midzone', env.get('HIPPOS_WHEEL_MIDZONE', ''),
    ]


@contextmanager
def wheel_proxy_context(ctx: LaunchContext, env: dict[str, str]):
    if not ctx.wheel:
        yield
        return

    wheel_procs: list[subprocess.Popen[str]] = []
    try:
        if not WHEEL_PROXY_BIN.exists():
            _log.warning("Wheel proxy helper not found: %s", WHEEL_PROXY_BIN)
            yield
            return

        for ctrl in ctx.controllers:
            if not ctrl.is_wheel or not ctrl.device_path:
                continue
            cmd = _wheel_proxy_command(ctrl, ctx, env)
            _log.info("Starting wheel proxy: %s", ' '.join(cmd))
            proc = subprocess.Popen(cmd, env=env, text=True)
            wheel_procs.append(proc)
            time.sleep(0.15)
            if proc.poll() is not None:
                raise RuntimeError(f"wheel proxy exited early for {ctrl.device_path} with code {proc.returncode}")

        yield
    finally:
        for proc in wheel_procs:
            try:
                proc.terminate()
            except Exception:
                pass
        for proc in wheel_procs:
            try:
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _gamescope_wrap(cmd: list[str], conf: dict[str, str]) -> list[str]:
    if not _conf_bool(conf, 'global.gamescope'):
        return cmd
    bin_path = which('gamescope')
    if bin_path is None:
        _log.warning("gamescope enabled but binary not found")
        return cmd

    gs = [bin_path]

    output_res = _conf_value(conf, 'global.gamescope_output_resolution', '')
    if output_res:
        w, _, h = output_res.partition('x')
        gs += ['-W', w, '-H', h]

    nested_res = _conf_value(conf, 'global.gamescope_nested_resolution', '')
    if nested_res:
        w, _, h = nested_res.partition('x')
        gs += ['-w', w, '-h', h]

    refresh = _conf_value(conf, 'global.gamescope_nested_refresh', '')
    if refresh:
        gs += ['-r', refresh]

    scaler = _conf_value(conf, 'global.gamescope_scaler', '')
    if scaler:
        gs += ['-S', scaler]

    filt = _conf_value(conf, 'global.gamescope_filter', '')
    if filt:
        gs += ['-F', filt]

    sharpness = _conf_value(conf, 'global.gamescope_sharpness', '')
    if sharpness:
        gs += ['--sharpness', sharpness]

    if _conf_bool(conf, 'global.gamescope_hdr'):
        gs.append('--hdr-enabled')

    extra_args = _conf_value(conf, 'global.gamescope_args', '-f -e')
    if extra_args.strip():
        gs += extra_args.split()

    gs.append('--')
    _log.info("gamescope wrap: %s", ' '.join(gs))
    return gs + cmd


def _run_game_command(
    ctx: LaunchContext,
    hotkey_name: str,
    cmd: list[str],
    env: dict[str, str],
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    conf = _load_hippos_conf()
    cmd = _gamescope_wrap(cmd, conf)
    if _hud_config_path() is not None and ctx.emulator in _HUD_NEEDS_WRAPPER and _hud_supported(ctx.system):
        cmd = ['mangohud'] + cmd
    with wheel_proxy_context(ctx, env):
        with hotkey_context(hotkey_name):
            profiles = _load_es_input_configs()
            with evmapy_context(ctx.system, ctx.emulator, ctx.rom, ctx.controllers, profiles):
                return subprocess.run(cmd, env=env, text=True, cwd=str(cwd) if cwd is not None else None)


# ── Libretro device types ─────────────────────────────────────────────────────

# Maps libretro core name → device ID for P1 (default joypad = 1)
_CORE_P1_DEVICE: dict[str, str] = {
    'atari800': '513', 'cap32': '513', '81': '259', 'fuse': '769',
    'mupen64plus_next': '1', 'parallel_n64': '1',
    'beetle_pce': '769', 'beetle_pce_fast': '769',  # PCE 6-button
    'genesisplusgx': '513', 'picodrive': '513',      # MD 6-button
    'genesis_plus_gx': '513',
    'prosystem': '1',   # 7800 pad
}
_CORE_P2_DEVICE: dict[str, str] = {
    'atari800': '513', 'fuse': '513',
    'genesisplusgx': '513', 'picodrive': '513',
    'genesis_plus_gx': '513',
}
# Maps system name → device ID (fallback when core has no entry)
_SYSTEM_P1_DEVICE: dict[str, str] = {
    'msx': '1', 'msx1': '1', 'msx2': '1', 'msx2+': '1', 'msxturbor': '1',
    'colecovision': '1',
}
_SYSTEM_P2_DEVICE: dict[str, str] = {
    'msx': '1', 'msx1': '1', 'msx2': '1', 'msx2+': '1', 'msxturbor': '1',
    'colecovision': '1',
}
# Systems with complex per-player config — handled inline
_COMPLEX_DEVICE_SYSTEMS: frozenset[str] = frozenset({
    'snes', 'nes', 'psx', 'megadrive', 'mastersystem', 'saturn', 'pce',
    'pcenginecd', 'supergrafx', 'wii', 'gamecube',
})


def _set_libretro_device_types(
    cfg: _KVConfig,
    ctx: LaunchContext,
    conf: dict[str, str],
) -> None:
    """Write input_libretro_device_pN keys to retroarch cfg."""
    core    = ctx.core
    system  = ctx.system
    nplayers = max((c.player for c in ctx.controllers), default=2)

    # Default: RETRO_DEVICE_JOYPAD = 1 for all ports
    for i in range(1, nplayers + 1):
        cfg.set(f'input_libretro_device_p{i}', '"1"')

    if system in _COMPLEX_DEVICE_SYSTEMS:
        _set_complex_device_types(cfg, ctx, conf, nplayers)
        return

    # Core-level override
    if core in _CORE_P1_DEVICE:
        cfg.set('input_libretro_device_p1', f'"{_CORE_P1_DEVICE[core]}"')
    elif system in _SYSTEM_P1_DEVICE:
        cfg.set('input_libretro_device_p1', f'"{_SYSTEM_P1_DEVICE[system]}"')

    if core in _CORE_P2_DEVICE:
        cfg.set('input_libretro_device_p2', f'"{_CORE_P2_DEVICE[core]}"')
    elif system in _SYSTEM_P2_DEVICE:
        cfg.set('input_libretro_device_p2', f'"{_SYSTEM_P2_DEVICE[system]}"')


def _set_complex_device_types(
    cfg: _KVConfig,
    ctx: LaunchContext,
    conf: dict[str, str],
    nplayers: int,
) -> None:
    system = ctx.system
    core   = ctx.core

    if system == 'snes':
        p1 = conf.get(f'controller1_{core}') or conf.get('controller1_snes9x', '1')
        p2 = conf.get(f'controller2_{core}') or conf.get('controller2_snes9x', '257')
        cfg.set('input_libretro_device_p1', f'"{p1}"')
        cfg.set('input_libretro_device_p2', f'"{p2}"')
        cfg.set('input_libretro_device_p3', f'"{conf.get("controller3_snes9x", "1")}"')

    elif system == 'nes':
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_nes", "1")}"')
        cfg.set('input_libretro_device_p2', f'"{conf.get("controller2_nes", "1")}"')

    elif system == 'psx':
        # DualShock = 517, DigitalController = 1, AnalogJoystick = 513
        for ctrl in ctx.controllers:
            val = conf.get(f'controller{ctrl.player}_psx', '517')
            cfg.set(f'input_libretro_device_p{ctrl.player}', f'"{val}"')

    elif system in ('megadrive',):
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_md", "513")}"')
        cfg.set('input_libretro_device_p2', f'"{conf.get("controller2_md", "513")}"')

    elif system == 'mastersystem':
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_ms", "769")}"')
        cfg.set('input_libretro_device_p2', f'"{conf.get("controller2_ms", "769")}"')

    elif system == 'saturn':
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_saturn", "1")}"')
        cfg.set('input_libretro_device_p2', f'"{conf.get("controller2_saturn", "1")}"')

    elif system in ('pce', 'pcenginecd', 'supergrafx'):
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_pce", "1")}"')

    elif system in ('wii', 'gamecube'):
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_wii", "1")}"')


# ── Netplay ────────────────────────────────────────────────────────────────────

_NETPLAY_MODES: frozenset[str] = frozenset({'host', 'client', 'spectator'})


def _write_retroarch_netplay(cfg: _KVConfig, ctx: LaunchContext) -> None:
    if ctx.netplay_mode not in _NETPLAY_MODES:
        return
    is_client = ctx.netplay_mode in ('client', 'spectator')
    cfg.set('netplay_mode',              '"true"' if is_client else '"false"')
    cfg.set('netplay_ip_port',           f'"{ctx.netplay_port}"')
    cfg.set('netplay_delay_frames',      '"0"')
    cfg.set('netplay_nickname',          f'"{_conf_value(_load_hippos_conf(), "global.netplay.nickname", "")}"')
    cfg.set('netplay_client_swap_input', '"false"')
    if is_client:
        cfg.set('netplay_ip_address', f'"{ctx.netplay_ip}"')
    _log.info("netplay: mode=%s ip=%s port=%s", ctx.netplay_mode, ctx.netplay_ip, ctx.netplay_port)


# ── Per-system input remapping ─────────────────────────────────────────────────

_REMAPS_DIR = RA_CONFIG_DIR / 'remaps'


def _write_retroarch_remapping(cfg: _KVConfig, ctx: LaunchContext) -> None:
    remap_dir = _REMAPS_DIR / ctx.system
    remap_file = remap_dir / f'{ctx.system}.rmp'
    if not remap_file.exists():
        return
    cfg.set('input_remapping_directory', f'"{remap_dir}"')
    cfg.set('input_remapping_path',      f'"{remap_file}"')
    _log.info("remapping: using %s", remap_file)


# Systems incompatible with rewind (too slow or causes crashes)
_SYSTEMS_NO_REWIND: frozenset[str] = frozenset({
    'sega32x', 'psx', 'zxspectrum', 'n64', 'n64dd',
    'dreamcast', 'atomiswave', 'naomi', 'naomi2', 'saturn',
})

# Systems incompatible with run-ahead (too demanding or causes issues)
_SYSTEMS_NO_RUNAHEAD: frozenset[str] = frozenset({
    'sega32x', 'n64', 'n64dd', 'dreamcast', 'atomiswave',
    'naomi', 'naomi2', 'saturn',
})

# Cores that require .slang shaders (Vulkan-only pipeline)
_CORES_FORCE_SLANG: frozenset[str] = frozenset({'mupen64plus_next'})

# ── RetroArch controller binding tables ────────────────────────────────────────

# ES input name → RetroArch button/trigger suffix
_RA_BTN_MAP: list[tuple[str, str]] = [
    ('a',        'a'),
    ('b',        'b'),
    ('x',        'x'),
    ('y',        'y'),
    ('start',    'start'),
    ('select',   'select'),
    ('pageup',   'l'),        # L1 / LB
    ('pagedown', 'r'),        # R1 / RB
    ('l2',       'l2'),       # L2 / LT — may be axis or button
    ('r2',       'r2'),       # R2 / RT
    ('l3',       'l3'),       # Left stick click
    ('r3',       'r3'),       # Right stick click
]

_RA_DPAD_MAP: list[tuple[str, str]] = [
    ('up',    'up'),
    ('down',  'down'),
    ('left',  'left'),
    ('right', 'right'),
]

# ES joystick axis name → RetroArch axis base name
# The ES name represents the negative/primary direction; we derive both ± from it.
_RA_AXIS_MAP: list[tuple[str, str]] = [
    ('joystick1left', 'l_x'),
    ('joystick1up',   'l_y'),
    ('joystick2left', 'r_x'),
    ('joystick2up',   'r_y'),
]

# SDL hat bitmask → RetroArch direction string
_HAT_DIR: dict[int, str] = {1: 'up', 2: 'right', 4: 'down', 8: 'left'}


def _ra_binding_value(binding: 'ESBinding') -> str:
    """Return RetroArch config value string for a binding (no quotes)."""
    if binding.type == 'button':
        return str(binding.code)
    if binding.type == 'axis':
        sign = '-' if binding.value < 0 else '+'
        return f'{sign}{binding.code}'
    if binding.type == 'hat':
        direction = _HAT_DIR.get(abs(binding.value), 'up')
        return f'h{binding.code}{direction}'
    return str(binding.code)


def _ra_type_suffix(binding: 'ESBinding') -> str:
    if binding.type == 'hat':
        return 'btn'
    return {'button': 'btn', 'axis': 'axis', 'key': 'key'}.get(binding.type, 'btn')


def _ra_analog_dpad_mode(profile: 'ESControllerProfile', system: str) -> str:
    """Return RetroArch analog_dpad_mode: '1' if dpad is buttons/hats (non-analog), else '0'."""
    if system in ('n64', 'n64dd', 'dreamcast', 'atomiswave', 'naomi', 'naomi2', '3ds'):
        return '0'
    for es_name in ('up', 'down', 'left', 'right'):
        b = profile.inputs.get(es_name)
        if b and b.type in ('button', 'hat'):
            return '1'
    return '0'


def _ra_btn_map_for_ctx(profile: 'ESControllerProfile', system: str, core: str, altlayout: str) -> dict[str, str]:
    """Return ES→RA button name map with all system/core-specific overrides applied."""
    btn_map = {es: ra for es, ra in _RA_BTN_MAP}

    # Fightstick layout: swap shoulder/trigger assignments
    if altlayout == 'fightstick':
        btn_map['pageup']   = 'l2'
        btn_map['pagedown'] = 'l'
        btn_map['l2']       = 'r2'
        btn_map['r2']       = 'r'

    # N64: if controller has no r2, promote pageup→l2 and l2→l (Z button fix)
    if system in ('n64', 'n64dd') and 'r2' not in profile.inputs:
        btn_map['pageup'] = 'l2'
        btn_map['l2']     = 'l'

    # Dreamcast/flycast: same r2-missing fix, plus r1/r2 swap
    if system == 'dreamcast' and core == 'flycast' and 'r2' not in profile.inputs:
        btn_map['pageup']   = 'l2'
        btn_map['l2']       = 'l'
        btn_map['pagedown'] = 'r2'
        btn_map['r2']       = 'r'

    # Yabasanshiro: reversed shoulders
    if core == 'yabasanshiro':
        btn_map['pageup']   = 'r'
        btn_map['pagedown'] = 'l'

    return btn_map


# ES button names for lightgun mapping
_RA_GUN_BTN_MAP: dict[str, str] = {
    'a':        'aux_a',
    'b':        'aux_b',
    'y':        'aux_c',
    'pageup':   'offscreen_shot',
    'pagedown': 'trigger',
    'start':    'start',
    'select':   'select',
}


def _write_retroarch_controller_bindings(
    cfg: '_KVConfig',
    controllers: list['ControllerInfo'],
    profiles: list['ESControllerProfile'],
    ctx: Optional['LaunchContext'] = None,
) -> None:
    """Write per-player button/axis/hat bindings derived from ES input profiles."""
    system   = ctx.system if ctx else ''
    core     = ctx.core   if ctx else ''
    lightgun = ctx.lightgun if ctx else False
    altlayout = ''
    if ctx:
        conf = _load_hippos_conf()
        altlayout = _conf_value(conf, f'{system}.altlayout', _conf_value(conf, 'global.altlayout', ''))

    for ctrl in controllers:
        n = ctrl.player
        profile = _pick_es_profile(profiles, ctrl)
        if profile is None:
            continue

        btn_map = _ra_btn_map_for_ctx(profile, system, core, altlayout)

        # Buttons and triggers
        for es_name, ra_name in btn_map.items():
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            suffix = _ra_type_suffix(binding)
            cfg.set(f'input_player{n}_{ra_name}_{suffix}', f'"{_ra_binding_value(binding)}"')

        # D-pad — also write gun_dpad_* variants for lightgun systems
        for es_name, ra_name in _RA_DPAD_MAP:
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            suffix = _ra_type_suffix(binding)
            val = f'"{_ra_binding_value(binding)}"'
            cfg.set(f'input_player{n}_{ra_name}_{suffix}', val)
            if lightgun:
                cfg.set(f'input_player{n}_gun_dpad_{ra_name}_{suffix}', val)

        # Lightgun gun button mapping
        if lightgun:
            for es_name, gun_name in _RA_GUN_BTN_MAP.items():
                binding = profile.inputs.get(es_name)
                if binding is None:
                    continue
                suffix = _ra_type_suffix(binding)
                cfg.set(f'input_player{n}_gun_{gun_name}_{suffix}', f'"{_ra_binding_value(binding)}"')

        # Analog sticks: write both ± directions from the single ES directional binding
        for es_name, ra_base in _RA_AXIS_MAP:
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            if binding.type != 'axis':
                continue
            primary_sign  = '-' if binding.value < 0 else '+'
            opposite_sign = '+' if primary_sign == '-' else '-'
            cfg.set(f'input_player{n}_{ra_base}_minus_axis', f'"{primary_sign}{binding.code}"')
            cfg.set(f'input_player{n}_{ra_base}_plus_axis',  f'"{opposite_sign}{binding.code}"')

        # analog_dpad_mode: '1' when dpad is buttons/hats so it also drives the analog stick
        cfg.set(f'input_player{n}_analog_dpad_mode', f'"{_ra_analog_dpad_mode(profile, system)}"')


# ── RetroArch config generator ─────────────────────────────────────────────────

class _KVConfig:
    """Simple key = value config file (retroarch format)."""

    def __init__(self, path: Path, separator: str = ' ') -> None:
        self.path = path
        self.sep = separator
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            parser = configparser.RawConfigParser()
            parser.optionxform = str  # preserve case
            parser.read_string('[DEFAULT]\n' + self.path.read_text(encoding='latin1'))
            self._data = dict(parser.items('DEFAULT'))
        except Exception as exc:
            _log.warning("Could not read %s: %s", self.path, exc)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def clear_prefix(self, prefix: str) -> None:
        for k in [k for k in self._data if k.startswith(prefix)]:
            del self._data[k]

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('w') as fh:
            for key, value in self._data.items():
                fh.write(f'{key}{self.sep}={self.sep}{value}\n')


def _write_retroarch_config(controllers: list[ControllerInfo], ctx: Optional[LaunchContext] = None) -> Path:
    conf = _load_hippos_conf()
    cfg = _KVConfig(RA_CUSTOM_CFG, separator=' ')

    # Paths
    cfg.set('savefile_directory',       f'"{SAVES}"')
    cfg.set('savestate_directory',      f'"{SAVES}"')
    cfg.set('screenshot_directory',     f'"{SCREENSHOTS}"')
    cfg.set('system_directory',         f'"{BIOS}"')
    cfg.set('core_options_path',        f'"{RA_CORES_CFG}"')
    cfg.set('assets_directory',         '"/usr/share/libretro/assets"')
    cfg.set('video_shader_dir',         f'"{HIPPOS_SHADERS}"')

    # Video
    cfg.set('video_fullscreen',         '"true"')
    cfg.set('video_threaded',           '"true"' if _conf_bool(conf, 'global.video_threaded') else '"false"')
    cfg.set('video_gpu_screenshot',     '"true"')
    cfg.set('aspect_ratio_index',       f'"{_ratio_index(conf)}"')

    cfg.set('video_smooth',             '"true"' if _conf_bool(conf, 'global.smooth') else '"false"')

    cfg.set('video_scale_integer',      '"true"' if _conf_bool(conf, 'global.integerscale') else '"false"')

    system = ctx.system if ctx is not None else ''
    rewind_ok = system not in _SYSTEMS_NO_REWIND
    cfg.set('rewind_enable', '"true"' if (_conf_bool(conf, 'global.rewind') and rewind_ok) else '"false"')

    runahead = _conf_int(conf, 'global.runahead', 0)
    runahead_ok = system not in _SYSTEMS_NO_RUNAHEAD
    cfg.set('run_ahead_enabled', '"false"')
    cfg.set('preemptive_frames_enable', '"false"')
    cfg.set('run_ahead_frames', '"0"')
    cfg.set('run_ahead_secondary_instance', '"false"')
    if runahead > 0 and runahead_ok:
        if _conf_bool(conf, 'global.preemptiveframes'):
            cfg.set('preemptive_frames_enable', '"true"')
        else:
            cfg.set('run_ahead_enabled', '"true"')
        cfg.set('run_ahead_frames', f'"{runahead}"')
        if _conf_bool(conf, 'global.secondinstance'):
            cfg.set('run_ahead_secondary_instance', '"true"')

    cfg.set('video_frame_delay_auto',   '"true"' if _conf_bool(conf, 'global.video_frame_delay_auto') else '"false"')
    cfg.set('vrr_runloop_enable',       '"true"' if _conf_bool(conf, 'global.vrr_runloop_enable') else '"false"')

    shaderset = conf.get('global.shaderset', 'none').strip()
    core = ctx.core if ctx is not None else ''
    shader_ext = 'slang' if core in _CORES_FORCE_SLANG else 'glslp'
    bezel_path = ctx.bezel if ctx is not None else None
    if bezel_path is not None:
        from hippos_bezels import SHADER_BEZEL, SHADER_BEZEL_DIR
        cfg.set('video_shader_enable', '"true"')
        cfg.set('video_shader_dir',    f'"{SHADER_BEZEL_DIR}"')
        cfg.set('video_shader',        f'"{SHADER_BEZEL}"')
    elif shaderset and shaderset != 'none':
        cfg.set('video_shader_enable', '"true"')
        cfg.set('video_shader', f'"{HIPPOS_SHADERS}/{shaderset}.{shader_ext}"')
    else:
        cfg.set('video_shader_enable', '"false"')

    # CRT mode — when switchres.ini is present, enable the switchres resolution
    # switching backend (mode 4) and tune the menu for low-resolution display.
    if Path('/etc/switchres.ini').exists():
        cfg.set('crt_switch_resolution',          '"4"')
        cfg.set('crt_switch_resolution_super',    '"0"')
        cfg.set('menu_driver',                    '"rgui"')
        cfg.set('menu_enable_widgets',            '"false"')
        cfg.set('notification_show_refresh_rate', '"false"')
        cfg.set('video_font_size',                '"10"')

    # Input
    # Autodetect disabled: we write complete explicit per-player bindings from ES
    # profiles. Enabling autodetect causes RetroArch to load its own autoconfig
    # profiles after the config is applied, which overrides our bindings.
    cfg.set('input_autodetect_enable',  '"false"')
    # udev driver reads /dev/input/event* directly — more reliable than sdl2
    # on Debian where SDL2 HIDAPI conflicts with xpad claiming the USB device.
    # Button indices are identical (both enumerate evdev BTN_* codes in order).
    cfg.set('input_joypad_driver',      '"udev"')
    cfg.set('input_enable_hotkey',      '"shift"')
    cfg.set('input_exit_emulator',      '"escape"')
    cfg.set('input_menu_toggle',        '"f1"')
    cfg.set('input_pause_toggle',       '"p"')
    cfg.set('input_save_state',         '"f3"')
    cfg.set('input_load_state',         '"f4"')
    cfg.set('input_screenshot',         '"nul"')
    # Load ES input profiles once — used for hotkey detection and button bindings
    _profiles = _load_es_input_configs()

    # Write the hotkey modifier button index so RetroArch uses the controller button
    # the user configured in ES rather than requiring Shift on keyboard.
    p1 = next((c for c in controllers if c.player == 1), None)
    if p1:
        _profile = _pick_es_profile(_profiles, p1)
        if _profile:
            _hk = _profile.inputs.get('hotkey')
            if _hk and _hk.type == 'button':
                cfg.set('input_enable_hotkey_btn', f'"{_hk.code}"')

    # Clear stale controller keys from any previous launch before rewriting
    cfg.clear_prefix('input_player')

    # Controller port assignments from ES detection
    for ctrl in controllers:
        cfg.set(f'input_player{ctrl.player}_joypad_index', f'"{ctrl.index}"')

    # Per-player button/axis/hat bindings from ES profiles (with system/core-specific remaps)
    _write_retroarch_controller_bindings(cfg, controllers, _profiles, ctx)

    # Libretro device types per core/system
    if ctx is not None:
        _set_libretro_device_types(cfg, ctx, conf)
        _write_retroarch_netplay(cfg, ctx)
        _write_retroarch_remapping(cfg, ctx)

    # Menu / UI
    cfg.set('notification_show_remap_load', '"false"')
    cfg.set('rgui_show_start_screen',   '"false"')
    cfg.set('content_show_favorites',   '"false"')
    cfg.set('content_show_images',      '"false"')
    cfg.set('content_show_music',       '"false"')
    cfg.set('content_show_video',       '"false"')
    cfg.set('content_show_history',     '"false"')
    cfg.set('content_show_playlists',   '"false"')
    cfg.set('menu_show_load_core',      '"false"')
    cfg.set('menu_show_online_updater', '"false"')
    cfg.set('menu_show_core_updater',   '"false"')

    # Save behaviour
    cfg.set('config_save_on_exit',      '"false"')
    cfg.set('log_to_file',              '"true"')
    cfg.set('log_dir',                  f'"{USERDATA / "system" / "logs"}"')
    cfg.set('log_to_file_timestamp',    '"false"')
    cfg.set('savestate_auto_save',      '"true"' if _conf_bool(conf, 'global.autosave') else '"false"')
    cfg.set('savestate_auto_load',      '"true"' if _conf_bool(conf, 'global.autosave') else '"false"')

    # RetroAchievements
    cheevos = _conf_bool(conf, 'global.retroachievements')
    cfg.set('cheevos_enable', '"true"' if cheevos else '"false"')
    if cheevos:
        username = conf.get('global.retroachievements.username', '')
        password = conf.get('global.retroachievements.password', '')
        hardcore = _conf_bool(conf, 'global.retroachievements.hardcore')
        if username:
            cfg.set('cheevos_username', f'"{username}"')
        if password:
            cfg.set('cheevos_password', f'"{password}"')
        cfg.set('cheevos_hardcore_mode_enable', '"true"' if hardcore else '"false"')

    cfg.set('input_rumble_gain', f'"{_conf_value(conf, "global.rumble_gain", "")}"')

    audio_vol = _conf_value(conf, 'global.audio_volume', '0')
    cfg.set('audio_volume', f'"{audio_vol}"')

    ai_enabled = _conf_bool(conf, 'global.ai_service_enabled')
    cfg.set('ai_service_enable', '"true"' if ai_enabled else '"false"')
    if ai_enabled:
        chosen_lang = _conf_value(conf, 'global.ai_target_lang', 'En')
        chosen_url = _conf_value(conf, 'global.ai_service_url', 'http://ztranslate.net/service?api_key=BATOCERA')
        cfg.set('ai_service_mode', '"0"')
        cfg.set('ai_service_source_lang', '"0"')
        cfg.set('ai_service_url', f'"{chosen_url}&mode=Fast&output=png&target_lang={chosen_lang}"')
        cfg.set('ai_service_pause', '"true"' if _conf_bool(conf, 'global.ai_service_pause') else '"false"')

    cfg.write()
    _log.info("Wrote retroarch config: %s", RA_CUSTOM_CFG)
    return RA_CUSTOM_CFG


def _write_retroarch_core_options(ctx: LaunchContext, conf: dict[str, str]) -> None:
    """Write per-core settings to retroarch-core-options.cfg."""
    RA_CORES_CFG.parent.mkdir(parents=True, exist_ok=True)
    opts: dict[str, str] = {}

    def _get(key: str, default: str = '') -> str:
        return conf.get(f'{ctx.system}.{key}') or conf.get(f'global.{key}', default)

    core = ctx.core

    if core in ('stella', 'stella2014'):
        opts['stella_console']             = _get('stella_console', 'auto')
        opts['stella_palette']             = _get('stella_palette', 'standard')
        opts['stella_filter']              = _get('stella_filter', 'disabled')
        opts['stella_crop_hoverscan']      = _get('stella_crop_hoverscan', 'disabled')
        opts['stella_ntsc_aspect']         = _get('stella_ntsc_aspect', 'par')
        opts['stella_phosphor']            = _get('stella_phosphor', 'auto')
        opts['stella_phosphor_blend']      = _get('stella_phosphor_blend', '60')

    elif core in ('snes9x', 'snes9x_next', 'bsnes', 'bsnes_mercury_balanced'):
        opts['snes9x_gfx_hires']          = _get('snes9x_gfx_hires', 'enabled')
        opts['snes9x_overscan']            = _get('snes9x_overscan', 'enabled')
        opts['snes9x_aspect']              = _get('snes9x_aspect', '4:3')
        opts['snes9x_region']              = _get('snes9x_region', 'auto')

    elif core in ('mgba',):
        opts['mgba_gb_model']             = _get('mgba_gb_model', 'Autodetect')
        opts['mgba_sgb_borders']          = _get('mgba_sgb_borders', 'ON')
        opts['mgba_frameskip']            = _get('mgba_frameskip', '0')
        opts['mgba_color_correction']     = _get('mgba_color_correction', 'OFF')

    elif core in ('gambatte',):
        opts['gambatte_gb_colorization']  = _get('gambatte_gb_colorization', 'disabled')
        opts['gambatte_gb_internal_palette'] = _get('gambatte_gb_internal_palette', 'GB - DMG')
        opts['gambatte_mix_frames']       = _get('gambatte_mix_frames', 'disabled')

    elif core in ('genesisplusgx', 'genesis_plus_gx', 'genesis_plus_gx_wide'):
        opts['genesis_plus_gx_system_hw'] = _get('genesis_plus_gx_system_hw', 'auto')
        opts['genesis_plus_gx_region_detect'] = _get('genesis_plus_gx_region_detect', 'auto')
        opts['genesis_plus_gx_aspect_ratio']  = _get('genesis_plus_gx_aspect_ratio', 'auto')
        opts['genesis_plus_gx_render']        = _get('genesis_plus_gx_render', 'single field')

    elif core in ('fceumm',):
        opts['fceumm_region']             = _get('fceumm_region', 'Auto')
        opts['fceumm_overscan']           = _get('fceumm_overscan', 'enabled')
        opts['fceumm_palette']            = _get('fceumm_palette', 'default')

    elif core in ('mesen',):
        opts['mesen_region']              = _get('mesen_region', 'Auto')
        opts['mesen_overscan_left']       = _get('mesen_overscan_left', '0')
        opts['mesen_overscan_right']      = _get('mesen_overscan_right', '0')
        opts['mesen_overscan_top']        = _get('mesen_overscan_top', '8')
        opts['mesen_overscan_bottom']     = _get('mesen_overscan_bottom', '8')

    elif core in ('beetle_pce', 'beetle_pce_fast'):
        opts['pce_cdimagedir']            = ''
        opts['pce_nospritelimit']         = _get('pce_nospritelimit', 'disabled')
        opts['pce_ocmultiplier']          = _get('pce_ocmultiplier', '1')
        opts['pce_aspect_ratio']          = _get('pce_aspect_ratio', 'auto')

    elif core in ('mame', 'mame2003_plus'):
        opts['mame_read_config']          = _get('mame_read_config', 'disabled')
        opts['mame_write_config']         = _get('mame_write_config', 'disabled')
        opts['mame_boot_to_bios']         = _get('mame_boot_to_bios', 'disabled')
        opts['mame_softlists_enable']     = _get('mame_softlists_enable', 'enabled')
        opts['mame_softlists_auto_media'] = _get('mame_softlists_auto_media', 'enabled')
        opts['mame_media_type']           = _get('mame_media_type', 'rom')

    elif core in ('fbneo', 'fbalpha'):
        opts['fbneo-lightgun-hide-crosshair'] = _get('fbneo_hide_crosshair', 'enabled')
        opts['fbneo-allow-patched-romsets']   = _get('fbneo_patched_roms', 'enabled')

    elif core in ('atari800', 'a5200'):
        if ctx.system == 'atari800':
            opts['atari800_system']       = _get('atari800_system', '800XL (64K)')
            opts['atari800_ntscpal']      = _get('atari800_ntscpal', 'NTSC')
            opts['atari800_sioaccel']     = _get('atari800_sioaccel', 'enabled')
        else:
            opts['atari800_system']       = '5200'
            opts['atari800_CartType']     = 'enabled'

    elif core in ('mupen64plus_next', 'parallel_n64'):
        opts['mupen64plus-rdp-plugin']    = _get('mupen64plus_rdp', 'gliden64')
        opts['mupen64plus-rsp-plugin']    = _get('mupen64plus_rsp', 'hle')
        opts['mupen64plus-43screensize']  = _get('mupen64plus_screensize', '640x480')
        opts['mupen64plus-169screensize'] = _get('mupen64plus_169screensize', '854x480')

    if not opts:
        return

    # Read existing options and merge (preserve user overrides)
    existing: dict[str, str] = {}
    if RA_CORES_CFG.exists():
        try:
            for line in RA_CORES_CFG.read_text().splitlines():
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, _, v = line.partition('=')
                    existing[k.strip()] = v.strip().strip('"')
        except OSError:
            pass

    # Only write defaults — don't overwrite user-set values
    for k, v in opts.items():
        if k not in existing:
            existing[k] = v

    lines = [f'{k} = "{v}"' for k, v in sorted(existing.items())]
    RA_CORES_CFG.write_text('\n'.join(lines) + '\n')
    _log.info("core options: wrote %d entries for core '%s'", len(opts), core)


def _write_retroarch_game_overrides(ctx: LaunchContext) -> Optional[Path]:
    if not ctx.lightgun and not ctx.wheel:
        return None

    cfg = _KVConfig(Path(f'/tmp/hippos-retroarch-{os.getpid()}-override.cfg'), separator=' ')

    if ctx.lightgun:
        for ctrl in ctx.controllers:
            cfg.set(f'input_player{ctrl.player}_mouse_index', '"0"')
        if ctx.core == 'nestopia':
            cfg.set('nestopia_zapper_device', '"lightgun"')
        elif ctx.core == 'fceux':
            cfg.set('fceumm_zapper_mode', '"lightgun"')
        elif ctx.core == 'mame2003-plus':
            cfg.set('mame2003-plus_xy_device', '"lightgun"')
        elif ctx.core == 'genesis_plus_gx':
            cfg.set('genesis_plus_gx_gun_input', '"lightgun"')
        elif ctx.core == 'stella':
            cfg.set('stella_lightgun_crosshair', '"enabled"')
        elif ctx.core == 'reicast':
            cfg.set('reicast_lightgun1_crosshair', '"Red"')
            cfg.set('reicast_lightgun2_crosshair', '"Blue"')
            cfg.set('reicast_lightgun3_crosshair', '"Green"')
            cfg.set('reicast_lightgun4_crosshair', '"White"')
        elif ctx.core == 'fbneo':
            cfg.set('fbneo-lightgun-crosshair-emulation', '"always show"')
        elif ctx.core == 'bsnes':
            cfg.set('bsnes_touchscreen_lightgun_superscope_reverse', '"OFF"')

    if ctx.wheel:
        if ctx.core in ('mupen64plus', 'mupen64plus_next', 'parallel_n64'):
            cfg.set('mupen64plus-astick-deadzone', '"0"')
            cfg.set('parallel-n64-astick-deadzone', '"0"')
        if ctx.core == 'reicast':
            cfg.set('reicast_analog_stick_deadzone', '"0%"')
        if ctx.core == 'beetle-saturn':
            cfg.set('beetle_saturn_analog_stick_deadzone', '"0%"')

    cfg.write()
    _log.info("Wrote retroarch overrides: %s", cfg.path)
    return cfg.path


# ── Video mode helpers ─────────────────────────────────────────────────────────

def _switch_video_mode(conf: dict[str, str], system: str) -> str:
    """Switch to per-game video mode. Returns previous mode string for restore."""
    original = subprocess.run(
        ['hippos-resolution', 'currentMode'],
        capture_output=True, text=True, check=False,
    ).stdout.strip()

    videomode = conf.get(f'{system}.videomode') or conf.get('crt.videomode', '') or conf.get('global.videomode', '')

    if _HAS_SWITCHRES and _switchres.is_available():
        # CRT active — use libswitchres.so directly to avoid XranR stale-mode accumulation.
        if videomode and videomode != 'default':
            parsed = _switchres.parse_videomode(videomode)
            if parsed:
                _log.info("videomode: CRT ctypes %s for '%s'", videomode, system)
                if _switchres.switch_to_mode(*parsed):
                    return original
                _log.warning("videomode: ctypes failed, falling back to subprocess")
        else:
            # No per-system mode — restore to boot resolution (already there on session start).
            boot_res = conf.get('crt.boot_resolution', '640x480i')
            parsed = _switchres.parse_videomode(boot_res)
            if parsed:
                _switchres.switch_to_mode(*parsed)
            return original

    if videomode and videomode != 'default':
        _log.info("videomode: setting '%s' for system '%s'", videomode, system)
        subprocess.run(
            ['hippos-resolution', 'setMode', videomode],
            check=False, stderr=subprocess.DEVNULL,
        )
    else:
        # Reduce 4K → ≤1080p; no-op if already within range.
        subprocess.run(
            ['hippos-resolution', 'minTomaxResolution'],
            check=False, stderr=subprocess.DEVNULL,
        )

    return original


def _prepare_ctx_bezel(ctx: LaunchContext, conf: dict[str, str]) -> None:
    """Resolve, resize, and stage bezel for this launch. Sets ctx.bezel."""
    from hippos_bezels import generate_gun_help, gun_border_color
    if ctx.resolution is None:
        return
    sys_bezel  = conf.get(f'{ctx.system}.bezel')
    bezel_name = sys_bezel if sys_bezel is not None else conf.get('global.bezel', '')
    if not bezel_name or bezel_name == 'none':
        generate_gun_help(ctx.system, ctx.rom, ctx.lightgun, ctx.game_gun, ctx.resolution)
        return
    stretch       = _conf_bool(conf, 'global.bezel_stretch')
    tattoo_type   = conf.get('global.bezel.tattoo', 'none')
    tattoo_file   = conf.get('global.bezel.tattoo_file')
    tattoo_corner = conf.get('global.bezel.tattoo_corner', 'NW')
    tattoo_resize = _conf_bool(conf, 'global.bezel.resize_tattoo', True)
    gun_border    = conf.get('global.use_guns') and conf.get('global.guns_borders_size', 'none') or 'none'
    gun_aspect    = conf.get('global.ratio')
    gun_col       = gun_border_color(conf)
    ra_game_id    = ctx.game_gun.get('ra_id') if ctx.lightgun else None
    qr_corner     = conf.get('global.bezel.qrcode_corner', 'NE')
    ctx.bezel = prepare_bezel(
        rom=ctx.rom,
        system=ctx.system,
        emulator=ctx.emulator,
        bezel_name=bezel_name,
        resolution=ctx.resolution,
        stretch=stretch,
        tattoo_type=tattoo_type,
        tattoo_file=tattoo_file,
        tattoo_corner=tattoo_corner,
        tattoo_resize=tattoo_resize,
        gun_border=gun_border,
        gun_aspect_ratio=gun_aspect,
        gun_border_col=gun_col,
        ra_game_id=ra_game_id,
        qr_corner=qr_corner,
    )
    generate_gun_help(ctx.system, ctx.rom, ctx.lightgun, ctx.game_gun, ctx.resolution)


def _restore_video_mode(original_mode: str, conf: dict[str, str] | None = None) -> None:
    if not original_mode:
        return
    _log.info("videomode: restoring '%s'", original_mode)
    if _HAS_SWITCHRES and _switchres.is_available():
        boot_res = (conf or {}).get('crt.boot_resolution', '640x480i')
        parsed   = _switchres.parse_videomode(boot_res)
        if parsed and _switchres.switch_to_mode(*parsed):
            return
        _log.warning("videomode: ctypes restore failed, falling back to subprocess")
    subprocess.run(
        ['hippos-resolution', 'setMode', original_mode],
        check=False, stderr=subprocess.DEVNULL,
    )


# ── Game environment builder ───────────────────────────────────────────────────

def _build_game_env(conf: dict[str, str], ctx: Optional[LaunchContext] = None) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault('DISPLAY', ':0')
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['HIPPOS_USE_GUNS'] = '1' if _conf_bool(conf, 'global.use_guns', True) else '0'
    env['HIPPOS_USE_WHEELS'] = '1' if _conf_bool(conf, 'global.use_wheels', True) else '0'
    env['HIPPOS_WHEEL_ROTATION'] = _conf_value(conf, 'wheel_rotation', '')
    env['HIPPOS_WHEEL_DEADZONE'] = _conf_value(conf, 'wheel_deadzone', '')
    env['HIPPOS_WHEEL_MIDZONE'] = _conf_value(conf, 'wheel_midzone', '')
    if ctx is not None and ctx.game_wheel:
        for key, value in ctx.game_wheel.items():
            env[f'HIPPOS_GAME_WHEEL_{key.upper()}'] = str(value)
        if ctx.game_wheel.get('rotation'):
            env['HIPPOS_WHEEL_ROTATION'] = ctx.game_wheel['rotation']
        if ctx.game_wheel.get('deadzone'):
            env['HIPPOS_WHEEL_DEADZONE'] = ctx.game_wheel['deadzone']
        if ctx.game_wheel.get('midzone'):
            env['HIPPOS_WHEEL_MIDZONE'] = ctx.game_wheel['midzone']
        env['HIPPOS_GAME_WHEEL_PRESENT'] = '1'
    else:
        env['HIPPOS_GAME_WHEEL_PRESENT'] = '0'
    if ctx is not None:
        for ctrl in ctx.controllers:
            prefix = f'HIPPOS_P{ctrl.player}_'
            env[f'{prefix}INDEX'] = str(ctrl.index)
            env[f'{prefix}GUID'] = ctrl.guid
            env[f'{prefix}NAME'] = ctrl.name
            env[f'{prefix}DEVICEPATH'] = ctrl.device_path
            env[f'{prefix}ISWHEEL'] = '1' if ctrl.is_wheel else '0'
            env[f'{prefix}WHEELROTATIONANGLE'] = str(ctrl.wheel_rotation_angle)
            env[f'{prefix}NBBUTTONS'] = str(ctrl.nb_buttons)
            env[f'{prefix}NBHATS'] = str(ctrl.nb_hats)
            env[f'{prefix}NBAXES'] = str(ctrl.nb_axes)
    if ctx is not None and ctx.controllers:
        env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    # Enable SDL2 HIDAPI Steam Controller support (works natively without steamd)
    env.setdefault('SDL_JOYSTICK_HIDAPI_STEAM', '1')
    # Force Xbox controllers to use the kernel xpad driver, not SDL2 HIDAPI.
    # xpad claims the USB device so HIDAPI has no hidraw node to open; SDL2 then
    # tries /dev/bus/usb which hippos cannot write to, silently drops the pad.
    env.setdefault('SDL_JOYSTICK_HIDAPI_XBOX_360', '0')
    env.setdefault('SDL_JOYSTICK_HIDAPI_XBOX_ONE', '0')
    env.setdefault('SDL_JOYSTICK_HIDAPI_XBOX', '0')
    hud_cfg = _hud_config_path()
    if hud_cfg is not None and (ctx is None or _hud_supported(ctx.system)):
        env['MANGOHUD_CONFIGFILE'] = str(hud_cfg)
        env['MANGOHUD_DLSYM'] = '1'
    if _conf_bool(conf, 'global.vkbasalt'):
        env['ENABLE_VKBASALT'] = '1'
    return env


# ── MangoHUD config generator ─────────────────────────────────────────────────

_HUD_CONFIG_PATH = Path('/var/run/hippos/hud.config')
_USER_HUD_CONFIG = HOME / 'hud.config'

# Emulators that cannot use DLSYM injection — need `mangohud` prepended to cmd.
_HUD_NEEDS_WRAPPER: frozenset[str] = frozenset({'wine', 'sh', 'flatpak'})


def _hud_config_path() -> Optional[Path]:
    """Return path to hud.config if HUD is active, else None."""
    conf = _load_hippos_conf()
    mode = conf.get('global.hud', 'none').strip()
    return _HUD_CONFIG_PATH if mode and mode != 'none' else None


def _build_hud_config(conf: dict[str, str], ctx: LaunchContext) -> Optional[Path]:
    """Generate /var/run/hippos/hud.config. Returns path or None if HUD disabled."""
    mode = conf.get('global.hud', 'none').strip()
    if not mode or mode == 'none':
        return None
    if conf.get(f'{ctx.system}.hud_support') == 'false':
        return None

    lines: list[str] = []

    # Bezel background — must come first
    if ctx.bezel is not None:
        lines.append(f'background_image={ctx.bezel}')
        lines.append('legacy_layout=false')

    if mode == 'perf':
        lines += [
            'fps',
            'frametime',
            'cpu_temp',
            'gpu_temp',
            'cpu_load',
            'gpu_load',
            'vram',
            'ram',
        ]
    elif mode == 'game':
        game_name = ctx.rom.stem
        # Try to read a nicer name from gameinfoxml
        if ctx.gameinfoxml and ctx.gameinfoxml.exists():
            try:
                root = ET.parse(ctx.gameinfoxml).getroot()
                name_el = root.find('.//name')
                if name_el is not None and name_el.text:
                    game_name = name_el.text.strip()
            except ET.ParseError:
                pass
        lines += [
            'fps',
            f'custom_text={game_name}',
            f'custom_text={ctx.system}',
            f'custom_text={ctx.emulator}/{ctx.core}' if ctx.core else f'custom_text={ctx.emulator}',
        ]
        # Thumbnail: check ES scraped image path convention
        thumb = ctx.rom.with_suffix('.png')
        if not thumb.exists():
            thumb = ctx.rom.parent / 'images' / f'{ctx.rom.stem}.png'
        if thumb.exists():
            lines.append(f'image={thumb}')
    elif mode == 'custom':
        if _USER_HUD_CONFIG.exists():
            lines += _USER_HUD_CONFIG.read_text().splitlines()
        else:
            _log.warning("hud: custom mode but %s not found, using perf", _USER_HUD_CONFIG)
            lines += ['fps', 'frametime', 'cpu_load', 'gpu_load']

    position = conf.get('global.hud_corner', 'top-left')
    lines.append(f'position={position}')

    _HUD_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HUD_CONFIG_PATH.write_text('\n'.join(lines) + '\n')
    _log.info("hud: config written (%s mode, %s)", mode, position)
    return _HUD_CONFIG_PATH


# ── Power mode hooks ──────────────────────────────────────────────────────────

def _battery_discharging() -> bool:
    for bat in Path('/sys/class/power_supply').glob('*BAT*'):
        status_file = bat / 'status'
        try:
            if status_file.exists() and status_file.read_text(encoding='utf-8').strip() == 'Discharging':
                return True
        except OSError:
            continue
    for bat in Path('/sys/class/power_supply').glob('*bat*'):
        status_file = bat / 'status'
        try:
            if status_file.exists() and status_file.read_text(encoding='utf-8').strip() == 'Discharging':
                return True
        except OSError:
            continue
    return False


def _available_governors() -> set[str]:
    available = set()
    candidate = Path('/sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors')
    try:
        if candidate.exists():
            available.update(candidate.read_text(encoding='utf-8').split())
    except OSError:
        pass
    return available


def _current_governor() -> str:
    candidate = Path('/sys/devices/system/cpu/cpufreq/policy0/scaling_governor')
    try:
        if candidate.exists():
            return candidate.read_text(encoding='utf-8').strip()
    except OSError:
        pass
    return ''


def _set_governor(governor: str) -> bool:
    gov = governor.strip()
    if not gov:
        return False
    available = _available_governors()
    if available and gov not in available:
        _log.info("Power mode governor '%s' not available (have: %s)", gov, ', '.join(sorted(available)))
        return False

    changed = False
    for gov_file in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor'):
        try:
            gov_file.write_text(gov, encoding='utf-8')
            changed = True
        except OSError:
            continue
    if changed:
        _log.info("Applied CPU governor: %s", gov)
    return changed


def _power_mode_to_governor(mode: str) -> str:
    normalized = mode.strip().lower()
    if not normalized or normalized == 'default':
        return ''
    if normalized in ('ac', 'performance', 'highperformance', 'high_performance'):
        return 'performance'
    if normalized in ('balanced', 'balance'):
        return 'schedutil'
    if normalized in ('battery', 'powersaver', 'power_saver', 'saver'):
        return 'powersave'
    return normalized


def _apply_game_power_mode(conf: dict[str, str], system: str, rom: Path) -> str:
    previous = _current_governor()
    if not system:
        return previous

    game_name = rom.stem
    keys = []
    if game_name:
        keys.append(f'{system}["{game_name}"].powermode')
    keys.append(f'{system}.powermode')
    keys.append('global.batterymode' if _battery_discharging() else 'global.powermode')

    selected = ''
    for key in keys:
        value = _conf_value(conf, key, '')
        if value:
            selected = value
            break

    governor = _power_mode_to_governor(selected)
    if governor:
        _set_governor(governor)
    return previous


def _restore_game_power_mode(previous: str) -> None:
    if previous:
        _set_governor(previous)


# ── Generators ─────────────────────────────────────────────────────────────────

def _write_unix_settings_file(path: Path, items: list[tuple[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fh:
        for key, value in items:
            fh.write(f'{key}={value}\n')


def _sync_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    # Guard: destination must not be inside source — syncing a dir into its own
    # subtree causes current/ to appear in source on the next run, then recurse
    # infinitely, eventually hitting PATH_MAX ("File name too long").
    try:
        destination.resolve().relative_to(source.resolve())
        __import__('logging').getLogger('hippos.emulatorlauncher').error(
            "_sync_tree: destination %s is inside source %s — refusing to sync",
            destination, source,
        )
        return
    except ValueError:
        pass
    destination.mkdir(parents=True, exist_ok=True)
    cmp = filecmp.dircmp(source, destination)
    for name in cmp.left_only + cmp.diff_files:
        src_path = source / name
        dst_path = destination / name
        if src_path.is_dir():
            _sync_tree(src_path, dst_path)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            copyfile(src_path, dst_path)
    for name in cmp.common_dirs:
        _sync_tree(source / name, destination / name)


def _amiberry_rom_type(rom: Path) -> str:
    extension = rom.suffix[1:].lower()
    if extension == 'lha':
        return 'WHDL'
    if extension == 'hdf':
        return 'HDF'
    if extension == 'uae':
        return 'UAE'
    if extension in ('iso', 'cue', 'chd'):
        return 'CD'
    if extension in ('adf', 'ipf'):
        return 'DISK'
    if extension == 'zip':
        try:
            with zipfile.ZipFile(rom) as zipf:
                for zipfilename in zipf.namelist():
                    if '/' in zipfilename:
                        continue
                    inner_ext = Path(zipfilename).suffix[1:].lower()
                    if inner_ext == 'info':
                        return 'WHDL'
                    if inner_ext == 'lha':
                        return 'UNKNOWN'
                    if inner_ext in ('adf', 'ipf'):
                        return 'DISK'
                    if inner_ext == 'uae':
                        return 'UAE'
        except Exception as exc:
            _log.warning("Could not inspect Amiberry zip %s: %s", rom, exc)
    return 'UNKNOWN'


from emulatorlauncher_generic import (
    launch_libretro as _launch_libretro,
    launch_standalone as _launch_standalone,
)
from emulatorlauncher_ports import (
    launch_eduke32 as _launch_eduke32,
    launch_theforceengine as _launch_theforceengine,
    launch_tr2x as _launch_tr2x,
    launch_sonic_mania as _launch_sonic_mania,
    launch_sonicretro as _launch_sonicretro,
    launch_sonic3air as _launch_sonic3air,
    launch_catacombgl as _launch_catacombgl,
    launch_fallout1_ce as _launch_fallout1_ce,
    launch_fallout2_ce as _launch_fallout2_ce,
)
from emulatorlauncher_runtime import (
    launch_amiberry as _launch_amiberry,
    launch_lindbergh_loader as _launch_lindbergh_loader,
    launch_solarus as _launch_solarus,
    launch_steam as _launch_steam,
    launch_wine as _launch_wine,
)
from emulatorlauncher_core import (
    launch_dolphin as _launch_dolphin,
    launch_duckstation as _launch_duckstation,
    launch_flycast as _launch_flycast,
    launch_mame as _launch_mame,
    launch_mupen64plus_qt as _launch_mupen64plus_qt,
)


from emulatorlauncher_gsplus import launch_gsplus as _launch_gsplus
from emulatorlauncher_misc import (
    launch_clk as _launch_clk,
    launch_flatpak as _launch_flatpak,
    launch_ioquake3 as _launch_ioquake3,
    launch_lexaloffle as _launch_lexaloffle,
    launch_lightspark as _launch_lightspark,
    launch_pygame as _launch_pygame,
    launch_pyxel as _launch_pyxel,
    launch_ruffle as _launch_ruffle,
    launch_sh as _launch_sh,
    launch_simcoupe as _launch_simcoupe,
    launch_tsugaru as _launch_tsugaru,
    launch_uqm as _launch_uqm,
    launch_vice as _launch_vice,
    launch_x16emu as _launch_x16emu,
    launch_redream as _launch_redream,
    launch_corsixth as _launch_corsixth,
    launch_gzdoom as _launch_gzdoom,
    launch_ryujinx as _launch_ryujinx,
)
from emulatorlauncher_model2emu import launch_model2emu as _launch_model2emu
from emulatorlauncher_play import launch_play as _launch_play
from emulatorlauncher_openbor import launch_openbor as _launch_openbor
from emulatorlauncher_shadps4 import launch_shadps4 as _launch_shadps4
from emulatorlauncher_supermodel import launch_supermodel as _launch_supermodel
from emulatorlauncher_vpinball import launch_vpinball as _launch_vpinball
from emulatorlauncher_xemu import launch_xemu as _launch_xemu
from emulatorlauncher_ares import launch_ares as _launch_ares
from emulatorlauncher_xenia import launch_xenia as _launch_xenia
from emulatorlauncher_computers import (
    launch_dosbox_staging,
    launch_dosbox_x,
    launch_hatari,
    launch_scummvm,
    launch_mupen64plus,
    launch_fsuae,
    launch_openmsx,
)
from emulatorlauncher_extras import (
    launch_xenia_edge,
    launch_citron_neo,
    launch_eden,
    launch_ymir,
    launch_xroar,
    launch_easyrpg,
    launch_thextech,
    launch_hypseus_singe,
    launch_tic80,
    launch_ikemen,
    launch_bigpemu,
    launch_applewin,
    launch_demul,
    launch_sugarbox,
)


# ── Per-emulator config generators ────────────────────────────────────────────

PPSSPP_CONFIG_DIR    = CONFIGS / 'ppsspp'
PPSSPP_INI           = PPSSPP_CONFIG_DIR / 'PSP' / 'SYSTEM' / 'ppsspp.ini'
PPSSPP_CONTROLS_INI  = PPSSPP_CONFIG_DIR / 'PSP' / 'SYSTEM' / 'controls.ini'

MELONDS_CONFIG_DIR = CONFIGS / 'melonDS'
MELONDS_TOML       = MELONDS_CONFIG_DIR / 'melonDS.toml'

VITA3K_CONFIG_DIR  = CONFIGS / 'vita3k'
VITA3K_CONFIG_FILE = VITA3K_CONFIG_DIR / 'config.yml'

AZAHAR_CONFIG_DIR  = CONFIGS / 'azahar-emu'
AZAHAR_INI         = AZAHAR_CONFIG_DIR / 'qt-config.ini'

CEMU_CONFIG_DIR         = USERDATA / '.config' / 'cemu'
CEMU_SETTINGS_XML       = CEMU_CONFIG_DIR / 'settings.xml'
CEMU_CONTROLLER_PROFILES = CEMU_CONFIG_DIR / 'controllerProfiles'

PCSX2_CONFIG_DIR   = CONFIGS / 'PCSX2'
PCSX2_INI          = PCSX2_CONFIG_DIR / 'inis' / 'PCSX2.ini'

RPCS3_CONFIG_DIR   = CONFIGS / 'rpcs3'
RPCS3_CONFIG_YML   = RPCS3_CONFIG_DIR / 'config.yml'


def _write_ppsspp_config(conf: dict[str, str]) -> None:
    """Write PPSSPP INI config from hippos.conf values."""
    PPSSPP_INI.parent.mkdir(parents=True, exist_ok=True)
    parser = _new_ini_parser()
    if PPSSPP_INI.exists():
        parser.read(PPSSPP_INI, encoding='utf-8')

    for section in ('Graphics', 'SystemParam', 'General', 'Upgrade'):
        _ensure_section(parser, section)

    # Graphics section
    parser.set('Graphics', 'GraphicsBackend',     _conf_value(conf, 'global.gfxbackend', '0 (OPENGL)'))
    parser.set('Graphics', 'InternalResolution',  _conf_value(conf, 'global.internal_resolution', '1'))
    parser.set('Graphics', 'SoftwareRenderer',    'False')
    parser.set('Graphics', 'FullScreen',          'True')
    vsync_val = _conf_value(conf, 'global.vsync', '0')
    parser.set('Graphics', 'VSync',               'True' if vsync_val == '1' else 'False')
    parser.set('Graphics', 'FrameSkip',           _conf_value(conf, 'global.frameskip', '0'))
    parser.set('Graphics', 'FrameSkipType',       '0')
    autoframeskip = _conf_value(conf, 'global.autoframeskip', '0')
    parser.set('Graphics', 'AutoFrameSkip',       'True' if autoframeskip == '1' else 'False')
    skip_buf = _conf_value(conf, 'global.skip_buffer_effects', 'False')
    parser.set('Graphics', 'SkipBufferEffects',   'True' if skip_buf == 'True' else 'False')
    cull = _conf_value(conf, 'global.disable_culling', '0')
    parser.set('Graphics', 'DisableRangeCulling', 'True' if cull == '1' else 'False')
    parser.set('Graphics', 'SkipGPUReadbackMode', _conf_value(conf, 'global.skip_gpu_readbacks', '0'))
    lazy = _conf_value(conf, 'global.lazy_texture_caching', '0')
    parser.set('Graphics', 'TextureBackoffCache', 'True' if lazy == '1' else 'False')
    parser.set('Graphics', 'SplineBezierQuality', _conf_value(conf, 'global.curves_quality', '2'))
    dup = _conf_value(conf, 'global.duplicate_frames', '0')
    parser.set('Graphics', 'RenderDuplicateFrames', 'True' if dup == '1' else 'False')
    parser.set('Graphics', 'InflightFrames',      _conf_value(conf, 'global.buffer_graphics', '3'))
    parser.set('Graphics', 'HardwareTransform',   'True')
    sw_skin = _conf_value(conf, 'global.software_skinning', '1')
    parser.set('Graphics', 'SoftwareSkinning',    'True' if sw_skin == '1' else 'False')
    hw_tess = _conf_value(conf, 'global.hardware_tessellation', '0')
    parser.set('Graphics', 'HardwareTessellation', 'True' if hw_tess == '1' else 'False')
    parser.set('Graphics', 'TexScalingType',      _conf_value(conf, 'global.texture_scaling_type', '0'))
    parser.set('Graphics', 'TexScalingLevel',     _conf_value(conf, 'global.texture_scaling_level', '1'))
    deposterize = _conf_value(conf, 'global.texture_deposterize', 'False')
    parser.set('Graphics', 'TexDeposterize',      'True' if deposterize == 'True' else 'False')
    parser.set('Graphics', 'AnisotropyLevel',     _conf_value(conf, 'global.anisotropic_filtering', '4'))
    parser.set('Graphics', 'TextureFiltering',    _conf_value(conf, 'global.texture_filtering', '1'))
    smart2d = _conf_value(conf, 'global.smart_2d', 'False')
    parser.set('Graphics', 'Smart2DTexFiltering', 'True' if smart2d == 'True' else 'False')
    parser.set('Graphics', 'DisplayIntegerScale', 'False')

    # SystemParam section
    parser.set('SystemParam', 'NickName',     'HippOS')
    parser.set('SystemParam', 'EncryptSave',  'False')
    parser.set('SystemParam', 'MemStickSize', '32')

    # General section
    parser.set('General', 'FirstRun',            'False')
    rewind = _conf_bool(conf, 'global.rewind')
    parser.set('General', 'RewindFlipFrequency', '300' if rewind else '0')
    cheats = _conf_value(conf, 'global.enable_cheats', 'False')
    parser.set('General', 'EnableCheats',        'True' if cheats == 'True' else 'False')
    parser.set('General', 'CheckForNewVersion',  'False')

    # Upgrade section - suppress update prompts
    parser.set('Upgrade', 'UpgradeMessage',   '')
    parser.set('Upgrade', 'UpgradeVersion',   '')
    parser.set('Upgrade', 'DismissedVersion', '')

    with PPSSPP_INI.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote PPSSPP config: %s", PPSSPP_INI)


# ── PPSSPP NKCode constants (from PPSSPP source) ──────────────────────────────
_PPSSPP_NKCODE = {
    'b':        189,  # A  → Circle
    'a':        190,  # B  → Cross
    'y':        191,  # X  → Triangle (note: ES y = Square label, PPSSPP Triangle)
    'x':        188,  # Y  → Square
    'select':   196,  # Select/Back
    'start':    197,  # Start
    'pageup':   193,  # L
    'pagedown': 192,  # R
    'up':        19,
    'down':      20,
    'left':      21,
    'right':     22,
}
_PPSSPP_HAT_DIR = {1: 19, 2: 22, 4: 20, 8: 21}  # SDL hat bitmask → NKCODE
_PPSSPP_AXIS_ID = {0: 0, 1: 1, 2: 11, 3: 14, 4: 17, 5: 18}  # SDL axis → PPSSPP axis
_PPSSPP_AXIS_BASE = 4000
_PPSSPP_DEVICE_BASE = 10  # DEVICE_ID_PAD_0

_PPSSPP_BTN_MAP: dict[str, str] = {
    'a': 'Circle', 'b': 'Cross', 'x': 'Triangle', 'y': 'Square',
    'start': 'Start', 'select': 'Select',
    'pageup': 'L', 'pagedown': 'R',
    'up': 'Up', 'down': 'Down', 'left': 'Left', 'right': 'Right',
}
_PPSSPP_AXIS_MAP: dict[str, tuple[str, str]] = {
    'joystick1left':  ('An.Left',       'An.Right'),
    'joystick1up':    ('An.Up',         'An.Down'),
    'joystick2left':  ('RightAn.Left',  'RightAn.Right'),
    'joystick2up':    ('RightAn.Up',    'RightAn.Down'),
}


def _ppsspp_axis_code(axis_id: int, direction: int) -> int:
    d = 1 if direction < 0 else 0
    return _PPSSPP_AXIS_BASE + axis_id * 2 + d


def _write_ppsspp_controls(ctx: LaunchContext) -> None:
    """Write PPSSPP controls.ini from the connected P1 ES controller profile."""
    PPSSPP_CONTROLS_INI.parent.mkdir(parents=True, exist_ok=True)
    profiles = _load_es_input_configs()
    p1 = next((c for c in ctx.controllers if c.player == 1), None)
    if p1 is None:
        return
    profile = _pick_es_profile(profiles, p1)
    if profile is None:
        return

    device_id = _PPSSPP_DEVICE_BASE + p1.index
    section = 'ControlMapping'

    parser = _new_ini_parser()
    _ensure_section(parser, section)

    def _append(key: str, val: str) -> None:
        existing = parser.get(section, key, fallback='')
        parser.set(section, key, f'{existing},{val}' if existing else val)

    # Buttons
    for es_name, ppsspp_name in _PPSSPP_BTN_MAP.items():
        binding = profile.inputs.get(es_name)
        if binding is None:
            continue
        if binding.type == 'button':
            nk = _PPSSPP_NKCODE.get(es_name)
            if nk is not None:
                _append(ppsspp_name, f'{device_id}-{nk}')
        elif binding.type == 'hat':
            nk = _PPSSPP_HAT_DIR.get(abs(binding.value))
            if nk is not None:
                _append(ppsspp_name, f'{device_id}-{nk}')
        elif binding.type == 'axis':
            raw_id = _PPSSPP_AXIS_ID.get(binding.code, binding.code)
            code = _ppsspp_axis_code(raw_id, binding.value)
            _append(ppsspp_name, f'{device_id}-{code}')

    # Analog sticks
    for es_name, (ppsspp_neg, ppsspp_pos) in _PPSSPP_AXIS_MAP.items():
        binding = profile.inputs.get(es_name)
        if binding is None or binding.type != 'axis':
            continue
        raw_id = _PPSSPP_AXIS_ID.get(binding.code, binding.code)
        neg_code = _ppsspp_axis_code(raw_id, -1)
        pos_code = _ppsspp_axis_code(raw_id, 1)
        _append(ppsspp_neg, f'{device_id}-{neg_code}')
        _append(ppsspp_pos, f'{device_id}-{pos_code}')

    # Hotkeys (keyboard bindings for F-keys)
    parser.set(section, 'Rewind',        '1-131')
    parser.set(section, 'Fast-forward',  '1-132')
    parser.set(section, 'Save State',    '1-133')
    parser.set(section, 'Load State',    '1-134')
    parser.set(section, 'Previous Slot', '1-135')
    parser.set(section, 'Next Slot',     '1-136')
    parser.set(section, 'Screenshot',    '1-137')
    parser.set(section, 'Pause',         '1-139')

    with PPSSPP_CONTROLS_INI.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote PPSSPP controls: %s", PPSSPP_CONTROLS_INI)


def _launch_ppsspp(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('ppsspp')
    if bin_path is None:
        _log.error("ppsspp not found")
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_ppsspp_config(conf)
    _write_ppsspp_controls(ctx)
    # --fullscreen and SDL_GAMECONTROLLERCONFIG without hotkey
    cmd = [str(bin_path), '--fullscreen', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    # PPSSPP uses hotkey button as menu toggle — exclude it from SDL mapping
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(
        ctx.controllers, ignore_buttons=['hotkey']
    )
    result = _run_game_command(ctx, 'ppsspp', cmd, env)
    return result.returncode


def _write_melonds_config(conf: dict[str, str]) -> None:
    """Write melonDS TOML config from hippos.conf values.

    melonDS uses a TOML config file. We use the _write_toml / _read_toml
    helpers already present in this module.
    """
    MELONDS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (SAVES / 'nds').mkdir(parents=True, exist_ok=True)

    existing = _read_toml(MELONDS_TOML)

    renderer = _conf_int(conf, 'global.melonds_renderer', 1)
    resolution = _conf_int(conf, 'global.melonds_resolution', 5)
    vsync = _conf_bool(conf, 'global.melonds_vsync', False)
    limit_fps = _conf_bool(conf, 'global.melonds_framerate', True)
    polygons = _conf_bool(conf, 'global.melonds_polygons', False)
    use_fw = _conf_bool(conf, 'global.melonds_use_fw_settings', False)
    language = _conf_int(conf, 'global.melonds_language', 1)
    rotation = _conf_int(conf, 'global.melonds_rotation', 0)
    screenswap = _conf_bool(conf, 'global.melonds_screenswap', False)
    layout = _conf_int(conf, 'global.melonds_layout', 0)
    screensizing = _conf_int(conf, 'global.melonds_screensizing', 0)
    scaling = _conf_bool(conf, 'global.melonds_scaling', False)

    base: dict[str, object] = {
        'MouseHide': False,
        'LastBIOSFolder': str(BIOS),
        'PauseLostFocus': False,
        'LimitFPS': limit_fps,
        'DS': {
            'FirmwarePath': str(BIOS / 'firmware.bin'),
            'BIOS7Path':    str(BIOS / 'bios7.bin'),
            'BIOS9Path':    str(BIOS / 'bios9.bin'),
        },
        'DLDI': {
            'FolderPath': str(SAVES / 'nds'),
            'ImagePath':  'dldi.bin',
            'Enable':     True,
        },
        'DSi': {
            'FirmwarePath': str(BIOS / 'dsi_firmware.bin'),
            'BIOS9Path':    str(BIOS / 'dsi_bios9.bin'),
            'BIOS7Path':    str(BIOS / 'dsi_bios7.bin'),
            'NANDPath':     str(BIOS / 'dsi_nand.bin'),
            'SD': {
                'FolderPath': str(SAVES / 'nds'),
                'ImagePath':  'dsisd.bin',
                'Enable':     True,
            },
        },
        'Emu': {
            'DirectBoot':         True,
            'ExternalBIOSEnable': True,
        },
        'Instance0': {
            'SaveFilePath':    str(SAVES / 'nds'),
            'SavestatePath':   str(SAVES / 'nds'),
            'EnableCheats':    False,
            'Firmware': {
                'OverrideSettings': use_fw,
                'Language':         language,
            },
            'Window0': {
                'ScreenRotation': rotation,
                'ScreenSwap':     screenswap,
                'ScreenLayout':   layout,
                'ScreenSizing':   screensizing,
                'IntegerScaling': scaling,
                'ShowOSD':        False,
            },
            'Window1': {
                'Enabled': False,
            },
        },
        '3D': {
            'Renderer': renderer,
            'GL': {
                'ScaleFactor':   resolution,
                'BetterPolygons': polygons,
            },
        },
        'Screen': {
            'VSync':  vsync,
            'UseGL':  renderer != 0,
        },
    }

    existing.update(base)
    _write_toml(MELONDS_TOML, existing)
    _log.info("Wrote melonDS config: %s", MELONDS_TOML)


def _launch_melonds(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('melonds')
    if bin_path is None:
        _log.error("melonds not found")
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_melonds_config(conf)
    cmd = [str(bin_path), '-f', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_DATA_HOME']   = str(SAVES)
    result = _run_game_command(ctx, 'melonds', cmd, env)
    return result.returncode


def _write_vita3k_config(conf: dict[str, str]) -> None:
    """Write Vita3K config.yml (YAML key-value pairs).

    ruamel.yaml is not guaranteed available; write raw YAML lines instead
    to preserve the vita3k format expectation. If yaml is available use it.
    """
    VITA3K_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (SAVES / 'psvita').mkdir(parents=True, exist_ok=True)

    backend    = _conf_value(conf, 'global.vita3k_gfxbackend', 'OpenGL')
    resolution = _conf_int(conf,   'global.vita3k_resolution', 1)
    fxaa_raw   = _conf_value(conf, 'global.vita3k_fxaa', '')
    vsync_raw  = _conf_value(conf, 'global.vita3k_vsync', '')
    aniso      = _conf_int(conf,   'global.vita3k_anisotropic', 1)
    linear_raw = _conf_value(conf, 'global.vita3k_linear', '')
    surface_raw = _conf_value(conf, 'global.vita3k_surface', '')

    fxaa    = 'true' if fxaa_raw.lower() in ('1', 'true', 'on') else 'false'
    vsync   = 'true' if vsync_raw == '' or vsync_raw.lower() in ('1', 'true', 'on') else 'false'
    linear  = 'true' if linear_raw.lower() in ('1', 'true', 'on') else 'false'
    surface = 'true' if surface_raw == '' or surface_raw.lower() in ('1', 'true', 'on') else 'false'

    if _HAS_YAML:
        existing: dict = {}
        if VITA3K_CONFIG_FILE.exists():
            try:
                existing = yaml.safe_load(VITA3K_CONFIG_FILE.read_text()) or {}
            except Exception:
                existing = {}
        existing['pref-path']            = str(SAVES / 'psvita')
        existing['backend-renderer']     = backend
        existing['resolution-multiplier'] = resolution
        existing['enable-fxaa']          = fxaa
        existing['v-sync']               = vsync
        existing['anisotropic-filtering'] = aniso
        existing['enable-linear-filter'] = linear
        existing['disable-surface-sync'] = surface
        VITA3K_CONFIG_FILE.write_text(yaml.dump(existing, default_flow_style=False))
    else:
        # Fallback: write minimal YAML key-value pairs
        lines = [
            '---',
            f'pref-path: {SAVES / "psvita"}',
            f'backend-renderer: {backend}',
            f'resolution-multiplier: {resolution}',
            f'enable-fxaa: {fxaa}',
            f'v-sync: {vsync}',
            f'anisotropic-filtering: {aniso}',
            f'enable-linear-filter: {linear}',
            f'disable-surface-sync: {surface}',
        ]
        VITA3K_CONFIG_FILE.write_text('\n'.join(lines) + '\n')

    _log.info("Wrote Vita3K config: %s", VITA3K_CONFIG_FILE)


def _launch_vita3k(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('vita3k')
    if bin_path is None:
        _log.error("vita3k not found")
        return 1
    (SAVES / 'psvita').mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_vita3k_config(conf)
    # Derive app ID from rom filename: e.g. [PCSA00011].psvita -> PCSA00011
    rom_stem = ctx.rom.stem
    begin, end = rom_stem.find('['), rom_stem.rfind(']')
    if 0 <= begin < end:
        app_id = rom_stem[begin + 1: end]
        app_dir = SAVES / 'psvita' / 'ux0' / 'app' / app_id
        if app_dir.is_dir():
            cmd = [str(bin_path), '-F', '-w', '-f', '-c', str(VITA3K_CONFIG_FILE), '-r', app_id]
        else:
            cmd = [str(bin_path), '-F', '-w', '-f', '-c', str(VITA3K_CONFIG_FILE), str(ctx.rom)]
    else:
        cmd = [str(bin_path), '-F', '-w', '-f', '-c', str(VITA3K_CONFIG_FILE), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    result = _run_game_command(ctx, 'vita3k', cmd, env, cwd=bin_path.parent)
    return result.returncode


def _write_azahar_config(conf: dict[str, str]) -> None:
    """Write Azahar qt-config.ini from hippos.conf values."""
    AZAHAR_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    parser = _new_ini_parser()
    if AZAHAR_INI.exists():
        parser.read(AZAHAR_INI, encoding='utf-8')

    for section in ('Layout', 'System', 'UI', 'Miscellaneous', 'Renderer', 'WebService', 'Utility'):
        _ensure_section(parser, section)

    # Layout
    screen_layout_raw = _conf_value(conf, 'global.azahar_screen_layout', '0-false')
    parts = screen_layout_raw.split('-', 1)
    layout_option = parts[0] if len(parts) > 0 else '0'
    swap_screen   = parts[1] if len(parts) > 1 else 'false'
    parser.set('Layout', 'custom_layout',    'false')
    parser.set('Layout', r'custom_layout\default', 'false')
    parser.set('Layout', 'swap_screen',      swap_screen)
    parser.set('Layout', r'swap_screen\default', 'false')
    parser.set('Layout', 'layout_option',    layout_option)
    parser.set('Layout', r'layout_option\default', 'false')
    parser.set('Layout', 'large_screen_proportion', _conf_value(conf, 'global.azahar_large_screen_proportion', '4'))
    parser.set('Layout', r'large_screen_proportion\default', 'false')

    # System
    is_new3ds = _conf_value(conf, 'global.azahar_is_new_3ds', '0')
    parser.set('System', 'is_new_3ds', 'true' if is_new3ds == '1' else 'false')
    parser.set('System', r'is_new_3ds\default', 'false')

    # UI
    parser.set('UI', 'fullscreen',    'true')
    parser.set('UI', r'fullscreen\default', 'false')
    parser.set('UI', 'displayTitleBars', 'false')
    parser.set('UI', r'displayTitleBars\default', 'false')
    parser.set('UI', 'firstStart',    'false')
    parser.set('UI', r'firstStart\default', 'false')
    parser.set('UI', 'hideInactiveMouse', 'true')
    parser.set('UI', r'hideInactiveMouse\default', 'false')
    parser.set('UI', 'enable_discord_presence', 'false')
    parser.set('UI', r'enable_discord_presence\default', 'false')
    parser.set('UI', 'calloutFlags', '1')
    parser.set('UI', r'calloutFlags\default', 'false')
    parser.set('UI', 'confirmClose', 'false')
    parser.set('UI', r'confirmClose\default', 'false')
    parser.set('UI', r'Paths\screenshotPath', str(SCREENSHOTS))
    parser.set('UI', r'Paths\screenshotPath\default', 'false')

    # Miscellaneous
    parser.set('Miscellaneous', 'check_for_update_on_start', 'false')
    parser.set('Miscellaneous', r'check_for_update_on_start\default', 'false')

    # Renderer
    graphics_api = _conf_value(conf, 'global.azahar_graphics_api', '1')
    parser.set('Renderer', 'graphics_api', graphics_api)
    parser.set('Renderer', r'graphics_api\default', 'true')
    use_hw = _conf_value(conf, 'global.azahar_use_hw_shader', '0')
    parser.set('Renderer', 'use_hw_shader', 'true' if use_hw == '1' else 'false')
    parser.set('Renderer', r'use_hw_shader\default', 'false')
    acc_mul = _conf_value(conf, 'global.azahar_accurate_multiplication', '0')
    parser.set('Renderer', 'shaders_accurate_mul', 'true' if acc_mul == '1' else 'false')
    parser.set('Renderer', r'shaders_accurate_mul\default', 'false')
    jit = _conf_value(conf, 'global.azahar_use_shader_jit', '1')
    parser.set('Renderer', 'use_shader_jit', 'true' if jit != '0' else 'false')
    parser.set('Renderer', r'use_hw_shader_jit\default', 'false')
    async_shaders = _conf_value(conf, 'global.azahar_async_shader_compilation', '0')
    parser.set('Renderer', 'async_shader_compilation', 'true' if async_shaders == '1' else 'false')
    parser.set('Renderer', r'async_shader_compilation\default', 'false')
    async_pres = _conf_value(conf, 'global.azahar_async_presentation', '0')
    parser.set('Renderer', 'async_presentation', 'true' if async_pres == '1' else 'false')
    parser.set('Renderer', r'async_presentation\default', 'false')
    vsync = _conf_value(conf, 'global.azahar_use_vsync_new', '1')
    parser.set('Renderer', 'use_vsync_new', 'true' if vsync != '0' else 'false')
    parser.set('Renderer', r'use_vsync_new\default', 'false')
    res_factor = _conf_value(conf, 'global.azahar_resolution_factor', '1')
    parser.set('Renderer', 'resolution_factor', res_factor)
    parser.set('Renderer', r'resolution_factor\default', 'false')

    # Utility
    disk_cache = _conf_value(conf, 'global.azahar_use_disk_shader_cache', '0')
    parser.set('Utility', 'use_disk_shader_cache', 'true' if disk_cache == '1' else 'false')
    parser.set('Utility', r'use_disk_shader_cache\default', 'false')

    # WebService
    parser.set('WebService', 'enable_telemetry', 'false')
    parser.set('WebService', r'enable_telemetry\default', 'false')

    with AZAHAR_INI.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote Azahar config: %s", AZAHAR_INI)


_AZAHAR_BUTTONS: dict[str, str] = {
    'button_a':      'a',      'button_b':     'b',
    'button_x':      'x',      'button_y':     'y',
    'button_up':     'up',     'button_down':  'down',
    'button_left':   'left',   'button_right': 'right',
    'button_l':      'pageup', 'button_r':     'pagedown',
    'button_start':  'start',  'button_select':'select',
    'button_zl':     'l2',     'button_zr':    'r2',
    'button_home':   'hotkey',
}
_AZAHAR_HAT_DIR: dict[int, str] = {1: 'up', 2: 'right', 4: 'down', 8: 'left'}


def _azahar_button_str(es_name: str, guid: str, inputs: dict) -> Optional[str]:
    binding = inputs.get(es_name)
    if binding is None:
        return None
    if binding.type == 'button':
        return f'button:{binding.code},guid:{guid},engine:sdl'
    if binding.type == 'hat':
        direction = _AZAHAR_HAT_DIR.get(abs(binding.value), 'up')
        return f'engine:sdl,guid:{guid},hat:{binding.code},direction:{direction}'
    if binding.type == 'axis':
        return f'engine:sdl,guid:{guid},axis:{binding.code},direction:+,threshold:0.5'
    return None


def _write_azahar_controller_config(ctx: LaunchContext) -> None:
    """Write Azahar Controls INI section from ES controller profile."""
    profiles = _load_es_input_configs()
    p1 = next((c for c in ctx.controllers if c.player == 1), None)
    if p1 is None:
        return
    profile = _pick_es_profile(profiles, p1)
    if profile is None:
        return

    cfg_path = AZAHAR_INI
    parser = _new_ini_parser()
    if cfg_path.exists():
        parser.read(cfg_path, encoding='utf-8')

    _ensure_section(parser, 'Controls')

    # Profile boilerplate
    if not parser.has_option('Controls', r'profiles\size'):
        parser.set('Controls', 'profile',                    '0')
        parser.set('Controls', r'profile\default',           'false')
        parser.set('Controls', r'profiles\1\name',           'default')
        parser.set('Controls', r'profiles\1\name\default',   'false')
        parser.set('Controls', r'profiles\size',             '1')
        parser.set('Controls', r'profiles\size\default',     'false')

    guid = p1.guid
    for ini_key, es_name in _AZAHAR_BUTTONS.items():
        val = _azahar_button_str(es_name, guid, profile.inputs)
        if val is not None:
            parser.set('Controls', rf'profiles\1\{ini_key}',           f'"{val}"')
            parser.set('Controls', rf'profiles\1\{ini_key}\default',   'false')

    # Analog sticks
    for ini_key, js_prefix in (('circle_pad', 'joystick1'), ('c_stick', 'joystick2')):
        bx = profile.inputs.get(f'{js_prefix}left')
        by = profile.inputs.get(f'{js_prefix}up')
        if bx and by and bx.type == 'axis' and by.type == 'axis':
            val = f'axis_x:{bx.code},guid:{guid},axis_y:{by.code},engine:sdl'
            parser.set('Controls', rf'profiles\1\{ini_key}',           f'"{val}"')
            parser.set('Controls', rf'profiles\1\{ini_key}\default',   'false')

    with cfg_path.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote Azahar controller config: %s", cfg_path)


def _launch_azahar(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('azahar')
    if bin_path is None:
        _log.error("azahar not found")
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_azahar_config(conf)
    _write_azahar_controller_config(ctx)
    cmd = [str(bin_path), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_DATA_HOME']   = str(SAVES / '3ds')
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    result = _run_game_command(ctx, 'azahar', cmd, env)
    return result.returncode


def _write_cemu_config(conf: dict[str, str]) -> None:
    """Write Cemu settings.xml from hippos.conf values using xml.etree.ElementTree."""
    import xml.etree.ElementTree as _ET

    CEMU_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (SAVES / 'wiiu').mkdir(parents=True, exist_ok=True)

    def _get_or_create(parent: _ET.Element, tag: str) -> _ET.Element:
        el = parent.find(tag)
        if el is None:
            el = _ET.SubElement(parent, tag)
        return el

    def _set_text(parent: _ET.Element, tag: str, text: str) -> None:
        el = _get_or_create(parent, tag)
        el.text = text

    if CEMU_SETTINGS_XML.exists():
        try:
            tree = _ET.parse(str(CEMU_SETTINGS_XML))
            root = tree.getroot()
        except Exception:
            root = _ET.Element('content')
    else:
        root = _ET.Element('content')

    # Root-level settings
    _set_text(root, 'mlc_path',           str(SAVES / 'wiiu'))
    _set_text(root, 'check_update',       'false')
    _set_text(root, 'gp_download',        'true')
    _set_text(root, 'logflag',            '0')
    _set_text(root, 'advanced_ppc_logging', 'false')
    _set_text(root, 'use_discord_presence', 'false')
    _set_text(root, 'fullscreen_menubar', 'false')
    _set_text(root, 'vk_warning',         'false')
    _set_text(root, 'fullscreen',         'true')

    # Language
    lang_val = _conf_value(conf, 'global.cemu_console_language', 'ui')
    if lang_val == 'ui':
        import os as _os
        lang = _os.environ.get('LANG', 'en_US')[:5]
    else:
        lang = lang_val
    lang_map = {'ja_JP': 0, 'en_US': 1, 'fr_FR': 2, 'de_DE': 3, 'it_IT': 4,
                'es_ES': 5, 'zh_CN': 6, 'ko_KR': 7, 'nl_NL': 8, 'pt_PT': 9,
                'ru_RU': 10, 'zh_TW': 11}
    _set_text(root, 'console_language', str(lang_map.get(lang, 1)))

    # Graphic section
    graphic = _get_or_create(root, 'Graphic')
    api_val = _conf_value(conf, 'global.cemu_gfxbackend', '1')
    _set_text(graphic, 'api',           api_val)
    async_val = _conf_value(conf, 'global.cemu_async', 'True')
    _set_text(graphic, 'AsyncCompile', 'true' if async_val.lower() in ('true', '1', 'on') else 'false')
    _set_text(graphic, 'VSync',        _conf_value(conf, 'global.cemu_vsync', '0'))
    _set_text(graphic, 'UpscaleFilter', _conf_value(conf, 'global.cemu_upscale', '2'))
    _set_text(graphic, 'DownscaleFilter', _conf_value(conf, 'global.cemu_downscale', '0'))
    _set_text(graphic, 'FullscreenScaling', _conf_value(conf, 'global.cemu_aspect', '0'))

    # Audio section
    audio = _get_or_create(root, 'Audio')
    _set_text(audio, 'api',         '3')  # cubeb
    _set_text(audio, 'TVChannels',  _conf_value(conf, 'global.cemu_audio_channels', '1'))
    _set_text(audio, 'TVVolume',    '100')

    # GamePaths
    game_paths = _get_or_create(root, 'GamePaths')
    _set_text(game_paths, 'Entry', str(USERDATA / 'roms' / 'wiiu'))

    tree = _ET.ElementTree(root)
    _ET.indent(tree, space='  ')
    with CEMU_SETTINGS_XML.open('wb') as fh:
        tree.write(fh, encoding='utf-8', xml_declaration=True)
    _log.info("Wrote Cemu config: %s", CEMU_SETTINGS_XML)


# Cemu SDL button index → Wii U GamePad/Pro mapping ID
_CEMU_GAMEPAD_BUTTONS = {
    "1": "1", "2": "0", "3": "3", "4": "2",
    "5": "9", "6": "10", "7": "42", "8": "43",
    "9": "6", "10": "4", "11": "11", "12": "12",
    "13": "13", "14": "14", "15": "7", "16": "8",
    "17": "45", "18": "39", "19": "44", "20": "38",
    "21": "47", "22": "41", "23": "46", "24": "40",
    "25": "7",
}
_CEMU_PRO_BUTTONS = {
    "1": "1", "2": "0", "3": "3", "4": "2",
    "5": "9", "6": "10", "7": "42", "8": "43",
    "9": "6", "10": "4",
    "12": "11", "13": "12", "14": "13", "15": "14",
    "16": "7", "17": "8",
    "18": "45", "19": "39", "20": "44", "21": "38",
    "22": "47", "23": "41", "24": "46", "25": "40",
}


def _write_cemu_controller_profiles(ctx: LaunchContext) -> None:
    """Write per-controller XML profiles for Cemu."""
    import xml.etree.ElementTree as _CET

    CEMU_CONTROLLER_PROFILES.mkdir(parents=True, exist_ok=True)

    # Remove stale profiles
    for old in CEMU_CONTROLLER_PROFILES.glob('controller*.xml'):
        old.unlink(missing_ok=True)

    for idx, ctrl in enumerate(ctx.controllers[:5]):
        controller_type = 'Wii U GamePad' if idx == 0 else 'Wii U Pro Controller'
        btn_map = _CEMU_GAMEPAD_BUTTONS if idx == 0 else _CEMU_PRO_BUTTONS

        root = _CET.Element('emulatedController')
        _CET.SubElement(root, 'type').text = controller_type
        _CET.SubElement(root, 'api').text = 'SDLController'
        _CET.SubElement(root, 'controllerIndex').text = str(ctrl.index)
        _CET.SubElement(root, 'rumble').text = 'false'
        _CET.SubElement(root, 'deadzone').text = '0.25'
        _CET.SubElement(root, 'range').text = '1'

        mappings = _CET.SubElement(root, 'mappings')
        for mapping_id, btn_id in btn_map.items():
            entry = _CET.SubElement(mappings, 'entry')
            _CET.SubElement(entry, 'mapping').text = mapping_id
            _CET.SubElement(entry, 'button').text = btn_id

        tree = _CET.ElementTree(root)
        _CET.indent(tree, space='  ')
        profile_path = CEMU_CONTROLLER_PROFILES / f'controller{idx}.xml'
        with profile_path.open('wb') as fh:
            tree.write(fh, encoding='utf-8', xml_declaration=True)

    _log.info("Wrote %d Cemu controller profiles", len(ctx.controllers[:5]))


def _launch_cemu(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('cemu')
    if bin_path is None:
        _log.error("cemu not found")
        return 1
    (SAVES / 'wiiu').mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_cemu_config(conf)
    _write_cemu_controller_profiles(ctx)
    cmd = [str(bin_path), '-f', '-g', str(ctx.rom), '--force-no-menubar']
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(USERDATA / '.config')
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    result = _run_game_command(ctx, 'cemu', cmd, env)
    return result.returncode


def _write_pcsx2_config(conf: dict[str, str], ctx: Optional['LaunchContext'] = None) -> None:
    """Write PCSX2 INI config from hippos.conf values."""
    PCSX2_INI.parent.mkdir(parents=True, exist_ok=True)
    (SAVES / 'ps2' / 'pcsx2' / 'sstates').mkdir(parents=True, exist_ok=True)
    (SAVES / 'ps2' / 'pcsx2').mkdir(parents=True, exist_ok=True)
    (CACHE / 'ps2').mkdir(parents=True, exist_ok=True)

    parser = _new_ini_parser()
    if PCSX2_INI.exists():
        parser.read(PCSX2_INI, encoding='utf-8')

    for section in ('UI', 'Folders', 'EmuCore', 'EmuCore/GS', 'Achievements', 'InputSources', 'Hotkeys'):
        _ensure_section(parser, section)

    # Clear saved window geometry — a crashed session can leave a tiny/corrupt position
    for key in ('MainWindowGeometry', 'MainWindowState'):
        if parser.has_option('UI', key):
            parser.remove_option('UI', key)

    # UI
    parser.set('UI', 'SettingsVersion',         '1')
    parser.set('UI', 'InhibitScreensaver',       'true')
    parser.set('UI', 'ConfirmShutdown',          'false')
    parser.set('UI', 'StartPaused',              'false')
    parser.set('UI', 'PauseOnFocusLoss',         'false')
    parser.set('UI', 'StartFullscreen',          'true')
    parser.set('UI', 'HideMouseCursor',          'true')
    parser.set('UI', 'RenderToSeparateWindow',   'false')
    parser.set('UI', 'HideMainWindowWhenRunning', 'true')
    parser.set('UI', 'DoubleClickTogglesFullscreen', 'false')

    # Folders — absolute paths; relative paths resolve from inis/ subdir and land wrong
    parser.set('Folders', 'Bios',        str(BIOS / 'ps2'))
    parser.set('Folders', 'Snapshots',   str(SCREENSHOTS))
    parser.set('Folders', 'Savestates',  str(SAVES / 'ps2' / 'pcsx2' / 'sstates'))
    parser.set('Folders', 'MemoryCards', str(SAVES / 'ps2' / 'pcsx2'))
    parser.set('Folders', 'Logs',        str(USERDATA / 'system' / 'logs'))
    parser.set('Folders', 'Cache',       str(CACHE / 'ps2'))
    parser.set('Folders', 'Textures',    str(PCSX2_CONFIG_DIR / 'textures'))

    # EmuCore
    parser.set('EmuCore', 'EnableDiscordPresence',       'false')
    fast_boot = _conf_value(conf, 'global.pcsx2_fastboot', '')
    parser.set('EmuCore', 'EnableFastBoot', 'false' if fast_boot == 'false' else 'true')
    parser.set('EmuCore', 'EnableCheats',                _conf_value(conf, 'global.pcsx2_cheats', 'false'))
    parser.set('EmuCore', 'EnableWideScreenPatches',     _conf_value(conf, 'global.pcsx2_EnableWideScreenPatches', 'false'))
    parser.set('EmuCore', 'EnableNoInterlacingPatches',  _conf_value(conf, 'global.pcsx2_interlacing_patches', 'false'))
    parser.set('EmuCore', 'SaveStateOnShutdown',         'true' if _conf_bool(conf, 'global.autosave') else 'false')

    # EmuCore/GS (graphics)
    parser.set('EmuCore/GS', 'Renderer',          _conf_value(conf, 'global.pcsx2_gfxbackend', '-1'))
    parser.set('EmuCore/GS', 'AspectRatio',        _conf_value(conf, 'global.pcsx2_ratio', 'Auto 4:3/3:2'))
    parser.set('EmuCore/GS', 'VsyncEnable',        _conf_value(conf, 'global.pcsx2_vsync', '0'))
    parser.set('EmuCore/GS', 'upscale_multiplier', _conf_value(conf, 'global.pcsx2_resolution', '1'))
    parser.set('EmuCore/GS', 'fxaa',               _conf_value(conf, 'global.pcsx2_fxaa', 'false'))
    parser.set('EmuCore/GS', 'FMVAspectRatioSwitch', _conf_value(conf, 'global.pcsx2_fmv_ratio', 'Auto 4:3/3:2'))
    parser.set('EmuCore/GS', 'mipmap_hw',          _conf_value(conf, 'global.pcsx2_mipmapping', '-1'))
    parser.set('EmuCore/GS', 'TriFilter',          _conf_value(conf, 'global.pcsx2_trilinear_filtering', '-1'))
    parser.set('EmuCore/GS', 'MaxAnisotropy',      _conf_value(conf, 'global.pcsx2_anisotropic_filtering', '0'))
    parser.set('EmuCore/GS', 'dithering_ps2',      _conf_value(conf, 'global.pcsx2_dithering', '2'))
    parser.set('EmuCore/GS', 'texture_preloading', _conf_value(conf, 'global.pcsx2_texture_loading', '2'))
    parser.set('EmuCore/GS', 'deinterlace_mode',   _conf_value(conf, 'global.pcsx2_deinterlacing', '0'))
    parser.set('EmuCore/GS', 'pcrtc_antiblur',     _conf_value(conf, 'global.pcsx2_blur', 'true'))
    parser.set('EmuCore/GS', 'IntegerScaling',     _conf_value(conf, 'global.pcsx2_scaling', 'false'))
    parser.set('EmuCore/GS', 'accurate_blending_unit', _conf_value(conf, 'global.pcsx2_blending', '1'))
    parser.set('EmuCore/GS', 'filter',             _conf_value(conf, 'global.pcsx2_texture_filtering', '2'))
    parser.set('EmuCore/GS', 'linear_present_mode', _conf_value(conf, 'global.pcsx2_bilinear_filtering', '1'))
    parser.set('EmuCore/GS', 'OsdShowMessages',    _conf_value(conf, 'global.pcsx2_osd_messages', 'true'))

    # Achievements
    parser.set('Achievements', 'Enabled',           'false')
    parser.set('Achievements', 'TestMode',           'false')
    parser.set('Achievements', 'UnofficialTestMode', 'false')
    parser.set('Achievements', 'Notifications',      'true')
    parser.set('Achievements', 'SoundEffects',       'true')

    # InputSources
    parser.set('InputSources', 'Keyboard', 'true')
    parser.set('InputSources', 'Mouse',    'true')
    parser.set('InputSources', 'SDL',      'true')

    # Hotkeys
    parser.set('Hotkeys', 'ToggleFullscreen', 'Keyboard/Alt & Keyboard/Return')
    parser.set('Hotkeys', 'LoadStateFromSlot', 'Keyboard/F3')
    parser.set('Hotkeys', 'SaveStateToSlot',   'Keyboard/F1')
    parser.set('Hotkeys', 'NextSaveStateSlot', 'Keyboard/F2')
    parser.set('Hotkeys', 'OpenPauseMenu',     'Keyboard/Escape')
    parser.set('Hotkeys', 'TogglePause',       'Keyboard/Space')

    # Pad / Multitap
    _ensure_section(parser, 'Pad')
    parser.set('Pad', 'MultitapPort1', 'false')
    parser.set('Pad', 'MultitapPort2', 'false')

    # Clear stale Pad1-Pad8 sections then rebuild from connected controllers
    for i in range(1, 9):
        if parser.has_section(f'Pad{i}'):
            parser.remove_section(f'Pad{i}')

    if ctx is not None:
        for nplayer, ctrl in enumerate(ctx.controllers[:8], start=1):
            pad = f'Pad{nplayer}'
            sdl  = f'SDL-{ctrl.index}'
            _ensure_section(parser, pad)
            parser.set(pad, 'Type',            'DualShock2')
            parser.set(pad, 'InvertL',         '0')
            parser.set(pad, 'InvertR',         '0')
            parser.set(pad, 'Deadzone',        '0')
            parser.set(pad, 'AxisScale',       '1.33')
            parser.set(pad, 'TriggerDeadzone', '0')
            parser.set(pad, 'TriggerScale',    '1')
            parser.set(pad, 'LargeMotorScale', '1')
            parser.set(pad, 'SmallMotorScale', '1')
            parser.set(pad, 'ButtonDeadzone',  '0')
            parser.set(pad, 'PressureModifier','0.5')
            parser.set(pad, 'Up',       f'{sdl}/DPadUp')
            parser.set(pad, 'Down',     f'{sdl}/DPadDown')
            parser.set(pad, 'Left',     f'{sdl}/DPadLeft')
            parser.set(pad, 'Right',    f'{sdl}/DPadRight')
            parser.set(pad, 'Triangle', f'{sdl}/FaceNorth')
            parser.set(pad, 'Circle',   f'{sdl}/FaceEast')
            parser.set(pad, 'Cross',    f'{sdl}/FaceSouth')
            parser.set(pad, 'Square',   f'{sdl}/FaceWest')
            parser.set(pad, 'Select',   f'{sdl}/Back')
            parser.set(pad, 'Start',    f'{sdl}/Start')
            parser.set(pad, 'L1',       f'{sdl}/LeftShoulder')
            parser.set(pad, 'R1',       f'{sdl}/RightShoulder')
            parser.set(pad, 'L2',       f'{sdl}/+LeftTrigger')
            parser.set(pad, 'R2',       f'{sdl}/+RightTrigger')
            parser.set(pad, 'L3',       f'{sdl}/LeftStick')
            parser.set(pad, 'R3',       f'{sdl}/RightStick')
            parser.set(pad, 'LUp',      f'{sdl}/-LeftY')
            parser.set(pad, 'LDown',    f'{sdl}/+LeftY')
            parser.set(pad, 'LLeft',    f'{sdl}/-LeftX')
            parser.set(pad, 'LRight',   f'{sdl}/+LeftX')
            parser.set(pad, 'RUp',      f'{sdl}/-RightY')
            parser.set(pad, 'RDown',    f'{sdl}/+RightY')
            parser.set(pad, 'RLeft',    f'{sdl}/-RightX')
            parser.set(pad, 'RRight',   f'{sdl}/+RightX')
            parser.set(pad, 'Analog',   f'{sdl}/Guide')
            parser.set(pad, 'LargeMotor', f'{sdl}/LargeMotor')
            parser.set(pad, 'SmallMotor', f'{sdl}/SmallMotor')

    with PCSX2_INI.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote PCSX2 config: %s", PCSX2_INI)


def _launch_pcsx2(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('pcsx2')
    if bin_path is None:
        _log.error("pcsx2 not found")
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_pcsx2_config(conf, ctx)
    # Write SDL controller DB
    pcsx2_db = PCSX2_INI.parent / 'game_controller_db.txt'
    pcsx2_db.parent.mkdir(parents=True, exist_ok=True)
    pcsx2_db.write_text(generate_sdl_game_controller_config(ctx.controllers))

    cmd = [str(bin_path), '-nogui', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    # Wheels break with SDL_GAMECONTROLLERCONFIG — exclude if wheel is active
    if ctx.wheel:
        env.pop('SDL_GAMECONTROLLERCONFIG', None)
    result = _run_game_command(ctx, 'pcsx2', cmd, env, cwd=bin_path.parent)
    return result.returncode


def _write_rpcs3_config(conf: dict[str, str]) -> None:
    """Write RPCS3 config.yml from hippos.conf values.

    RPCS3 uses YAML format. We use the yaml module if available,
    otherwise write raw YAML text.
    """
    RPCS3_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if _HAS_YAML and RPCS3_CONFIG_YML.exists():
        try:
            existing = yaml.safe_load(RPCS3_CONFIG_YML.read_text()) or {}
        except Exception:
            existing = {}

    # Ensure top-level keys exist
    for key in ('Core', 'Video', 'Audio', 'Input/Output', 'Miscellaneous'):
        if key not in existing:
            existing[key] = {}

    # Core
    existing['Core']['PPU Decoder']           = _conf_value(conf, 'global.rpcs3_ppudecoder', 'Recompiler (LLVM)')
    existing['Core']['SPU Decoder']           = _conf_value(conf, 'global.rpcs3_spudecoder', 'Recompiler (LLVM)')
    existing['Core']['XFloat Accuracy']       = _conf_value(conf, 'global.rpcs3_spuxfloataccuracy', 'Approximate')
    existing['Core']['SPU Cache']             = True
    existing['Core']['Preferred SPU Threads'] = _conf_int(conf, 'global.rpcs3_sputhreads', 0)
    existing['Core']['SPU loop detection']    = _conf_bool(conf, 'global.rpcs3_spuloopdetection', False)
    existing['Core']['SPU Block Size']        = _conf_value(conf, 'global.rpcs3_spublocksize', 'Safe')
    existing['Core']['Sleep Timers Accuracy'] = _conf_value(conf, 'global.rpcs3_sleep_timers_accuracy', 'As Host')

    # Video
    gfxbackend = _conf_value(conf, 'global.rpcs3_gfxbackend', '')
    existing['Video']['Renderer']          = 'OpenGL' if gfxbackend == 'OpenGL' else 'Vulkan'
    ratio = _conf_value(conf, 'global.rpcs3_ratio', '')
    existing['Video']['Aspect ratio']      = ratio if ratio else '16:9'
    existing['Video']['Shader Mode']       = _conf_value(conf, 'global.rpcs3_shadermode', 'Async Shader Recompiler')
    existing['Video']['VSync']             = _conf_bool(conf, 'global.rpcs3_vsync', False)
    existing['Video']['Stretch To Display Area'] = _conf_bool(conf, 'global.rpcs3_stretchdisplay', False)
    existing['Video']['Write Color Buffers'] = _conf_bool(conf, 'global.rpcs3_colorbuffers', False)
    existing['Video']['Disable Vertex Cache'] = _conf_bool(conf, 'global.rpcs3_vertexcache', False)
    existing['Video']['Anisotropic Filter Override'] = _conf_int(conf, 'global.rpcs3_anisotropic', 0)
    existing['Video']['MSAA']             = _conf_value(conf, 'global.rpcs3_aa', 'Auto')
    existing['Video']['Shader Precision'] = _conf_value(conf, 'global.rpcs3_shader', 'High')
    existing['Video']['Resolution']       = '1280x720'
    existing['Video']['Resolution Scale'] = _conf_int(conf, 'global.rpcs3_resolution_scale', 100)
    existing['Video']['Output Scaling Mode'] = _conf_value(conf, 'global.rpcs3_scaling', 'Bilinear')
    existing['Video']['Shader Compiler Threads'] = _conf_int(conf, 'global.rpcs3_num_compilers', 0)
    existing['Video']['Multithreaded RSX'] = _conf_bool(conf, 'global.rpcs3_rsx', False)
    existing['Video']['Asynchronous Texture Streaming 2'] = _conf_bool(conf, 'global.rpcs3_async_texture', False)
    existing['Video']['Write Depth Buffer'] = _conf_bool(conf, 'global.rpcs3_write_depth_buffers', False)
    framelimit = _conf_value(conf, 'global.rpcs3_framelimit', '')
    if not framelimit:
        existing['Video']['Frame limit'] = 'Auto'
        existing['Video']['Second Frame Limit'] = 0
    elif framelimit in ('Off', '30', '50', '59.94', '60'):
        existing['Video']['Frame limit'] = framelimit
        existing['Video']['Second Frame Limit'] = 0
    else:
        existing['Video']['Frame limit'] = 'Off'
        try:
            existing['Video']['Second Frame Limit'] = float(framelimit)
        except ValueError:
            existing['Video']['Second Frame Limit'] = 0

    # Audio
    existing['Audio']['Renderer']          = 'Cubeb'
    existing['Audio']['Master Volume']     = 100
    existing['Audio']['Enable Buffering']  = _conf_bool(conf, 'global.rpcs3_audiobuffer', True)
    existing['Audio']['Desired Audio Buffer Duration'] = _conf_int(conf, 'global.rpcs3_audiobuffer_duration', 100)
    if _conf_bool(conf, 'global.rpcs3_timestretch', False):
        existing['Audio']['Enable Time Stretching'] = True
        existing['Audio']['Enable Buffering']       = True
    else:
        existing['Audio']['Enable Time Stretching'] = False

    # Miscellaneous
    existing['Miscellaneous']['Exit RPCS3 when process finishes']  = True
    existing['Miscellaneous']['Start games in fullscreen mode']    = True
    existing['Miscellaneous']['Show shader compilation hint']      = False
    existing['Miscellaneous']['Prevent display sleep while running games'] = True
    existing['Miscellaneous']['Show trophy popups']                = False

    if _HAS_YAML:
        RPCS3_CONFIG_YML.write_text(yaml.dump(existing, default_flow_style=False, allow_unicode=True))
    else:
        # Fallback: write minimal YAML without lists
        lines = ['---']
        for section, items in existing.items():
            lines.append(f'{section}:')
            if isinstance(items, dict):
                for k, v in items.items():
                    if isinstance(v, bool):
                        lines.append(f'  {k}: {str(v).lower()}')
                    else:
                        lines.append(f'  {k}: {v}')
        RPCS3_CONFIG_YML.write_text('\n'.join(lines) + '\n')

    _log.info("Wrote RPCS3 config: %s", RPCS3_CONFIG_YML)


_RPCS3_INPUT_DIR = RPCS3_CONFIG_DIR / 'input_configs' / 'global'

_RPCS3_SONY_GUIDS: frozenset[str] = frozenset({
    # DS3
    '030000004c0500006802000011010000', '030000004c0500006802000011810000',
    '050000004c0500006802000000800000', '050000004c0500006802000000000000',
    # DS4
    '030000004c050000c405000011810000', '050000004c050000c405000000810000',
    '030000004c050000cc09000011010000', '050000004c050000cc09000000010000',
    '030000004c050000cc09000011810000', '050000004c050000cc09000000810000',
    '030000004c050000a00b000011010000', '030000004c050000a00b000011810000',
    # DS5
    '030000004c050000e60c000011810000', '050000004c050000e60c000000810000',
})

_RPCS3_EVDEV_MAP = [
    ('up',          'Up',              'BTN_DPAD_UP',   'ABS_HAT0Y', 'Hat0 Y-'),
    ('down',        'Down',            'BTN_DPAD_DOWN', 'ABS_HAT0Y', 'Hat0 Y+'),
    ('left',        'Left',            'BTN_DPAD_LEFT', 'ABS_HAT0X', 'Hat0 X-'),
    ('right',       'Right',           'BTN_DPAD_RIGHT','ABS_HAT0X', 'Hat0 X+'),
    ('l2',          'L2',              'BTN_TL2',       'ABS_Z',     'LZ+'),
    ('r2',          'R2',              'BTN_TR2',       'ABS_RZ',    'RZ+'),
    ('a',           'Cross',           'BTN_A',         None,        None),
    ('b',           'Circle',          'BTN_B',         None,        None),
    ('x',           'Square',          'BTN_X',         None,        None),
    ('y',           'Triangle',        'BTN_Y',         None,        None),
    ('joystick1up', 'Left Stick Up',   None,            'ABS_Y',     'LY-'),
    ('joystick1left','Left Stick Left',None,            'ABS_X',     'LX-'),
    ('joystick2up', 'Right Stick Up',  None,            'ABS_RY',    'RY-'),
    ('joystick2left','Right Stick Left',None,           'ABS_RX',    'RX-'),
]


def _write_rpcs3_controller_config(ctx: LaunchContext) -> None:
    """Write RPCS3 Default.yml input config."""
    _RPCS3_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    conf      = _load_hippos_conf()
    profiles  = _load_es_input_configs()
    ds3_count = ds4_count = ds5_count = 1

    config_path = _RPCS3_INPUT_DIR / 'Default.yml'
    with config_path.open('w', encoding='utf-8-sig') as f:
        for nplayer, ctrl in enumerate(ctx.controllers[:7], start=1):
            guid = ctrl.guid.lower()
            ctrl_type = conf.get(f'rpcs3_controller{nplayer}', '')
            rumble    = 'false' if not _conf_bool(conf, f'rpcs3_rumble{nplayer}', True) else 'true'

            if guid in _RPCS3_SONY_GUIDS and ctrl_type == 'Sony':
                # Sony native handler
                ds3_guids = list(_RPCS3_SONY_GUIDS)[:4]
                ds4_guids = list(_RPCS3_SONY_GUIDS)[4:12]
                if guid in ds3_guids:
                    f.write(f'Player {nplayer} Input:\n')
                    f.write('  Handler: DualShock 3\n')
                    f.write(f'  Device: "DS3 Pad #{ds3_count}"\n')
                    ds3_count += 1
                elif guid in ds4_guids:
                    f.write(f'Player {nplayer} Input:\n')
                    f.write('  Handler: DualShock 4\n')
                    f.write(f'  Device: "DS4 Pad #{ds4_count}"\n')
                    ds4_count += 1
                else:
                    f.write(f'Player {nplayer} Input:\n')
                    f.write('  Handler: DualSense\n')
                    f.write(f'  Device: "DualSense Pad #{ds5_count}"\n')
                    ds5_count += 1
                f.write('  Config:\n')
                for line in (
                    '    Left Stick Left: LS X-',  '    Left Stick Down: LS Y-',
                    '    Left Stick Right: LS X+', '    Left Stick Up: LS Y+',
                    '    Right Stick Left: RS X-', '    Right Stick Down: RS Y-',
                    '    Right Stick Right: RS X+','    Right Stick Up: RS Y+',
                    '    Start: Options',           '    Select: Share',
                    '    PS Button: PS Button',     '    Square: Square',
                    '    Cross: Cross',             '    Circle: Circle',
                    '    Triangle: Triangle',       '    Left: Left',
                    '    Down: Down',               '    Right: Right',
                    '    Up: Up',                   '    R1: R1',
                    '    R2: R2',                   '    R3: R3',
                    '    L1: L1',                   '    L2: L2',
                    '    L3: L3',
                    '    Left Stick Deadzone: 40',  '    Right Stick Deadzone: 40',
                    '    Left Trigger Threshold: 0','    Right Trigger Threshold: 0',
                    '    Left Stick Multiplier: 100','    Right Stick Multiplier: 100',
                    f'    Enable Large Vibration Motor: {rumble}',
                    f'    Enable Small Vibration Motor: {rumble}',
                ):
                    f.write(line + '\n')
                f.write('  Buddy Device: ""\n')

            else:
                # Evdev handler — maps ES inputs to evdev event names
                profile = _pick_es_profile(profiles, ctrl)
                f.write(f'Player {nplayer} Input:\n')
                f.write('  Handler: Evdev\n')
                f.write(f'  Device: {ctrl.device_path or "/dev/input/js0"}\n')
                f.write('  Config:\n')
                f.write('    Start: Start\n')
                f.write('    Select: Select\n')
                f.write('    PS Button: Mode\n')

                if profile is not None:
                    for es_name, cfg_name, btn_evt, axis_evt, axis_val in _RPCS3_EVDEV_MAP:
                        binding = profile.inputs.get(es_name)
                        if binding is None:
                            continue
                        if binding.type == 'button' and btn_evt:
                            f.write(f'    {cfg_name}: {btn_evt.replace("BTN_", "").capitalize()}\n')
                        elif binding.type in ('hat', 'axis') and axis_evt and axis_val:
                            f.write(f'    {cfg_name}: {axis_val}\n')

                f.write('    Left Stick Deadzone: 30\n')
                f.write('    Right Stick Deadzone: 30\n')
                f.write(f'    Enable Large Vibration Motor: {rumble}\n')
                f.write(f'    Enable Small Vibration Motor: {rumble}\n')
                f.write('  Buddy Device: ""\n')

    _log.info("Wrote RPCS3 controller config: %s", config_path)


def _launch_rpcs3(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('rpcs3')
    if bin_path is None:
        _log.error("rpcs3 not found")
        return 1
    (SAVES / 'ps3').mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_rpcs3_config(conf)
    _write_rpcs3_controller_config(ctx)
    # Determine ROM path
    rom = ctx.rom
    if rom.suffix.lower() == '.ink':
        # .ink shortcut: text file containing path to PS3 game directory
        try:
            target = Path(rom.read_text().strip())
            if target.is_dir():
                rom = target / 'PS3_GAME' / 'USRDIR' / 'EBOOT.BIN'
            else:
                rom = target
        except Exception:
            pass
    if rom.suffix == '.psn':
        game_id = None
        try:
            for line in rom.read_text().splitlines():
                if len(line) >= 9:
                    game_id = line.strip().upper()
        except Exception:
            pass
        if game_id:
            eboot = RPCS3_CONFIG_DIR / 'dev_hdd0' / 'game' / game_id / 'USRDIR' / 'EBOOT.BIN'
            rom = eboot
    elif rom.is_dir():
        rom = rom / 'PS3_GAME' / 'USRDIR' / 'EBOOT.BIN'
    cmd = [str(bin_path), '--no-gui', str(rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_CACHE_HOME']  = str(CACHE)
    result = _run_game_command(ctx, 'rpcs3', cmd, env)
    return result.returncode


# Emulators that write saves inside the ROM directory (squashfs ports etc.).
# These get an overlayfs layer so writes persist to /userdata/saves.
WRITES_TO_ROM: frozenset[str] = frozenset({
    'sh',
    'solarus',
    'pygame',
    'pyxel',
    'thextech',
})

# Maps emulator name → generator function.
# libretro is handled specially; everything else goes through _launch_standalone
# until it gets its own generator.
GENERATORS: dict[str, Callable[[LaunchContext], int]] = {
    'libretro':    _launch_libretro,
    'sh':          _launch_sh,
    'duckstation': _launch_duckstation,
    'pcsx2':       _launch_pcsx2,
    'dolphin':     _launch_dolphin,
    'dolphin-emu': _launch_dolphin,
    'dosbox':         launch_dosbox_staging,
    'dosbox-x':       launch_dosbox_x,
    'dosbox_staging': launch_dosbox_staging,
    'dosboxx':        launch_dosbox_x,
    'amiberry':    _launch_amiberry,
    'applewin':    launch_applewin,
    'bigpemu':     launch_bigpemu,
    'abuse':       _launch_standalone,
    'bstone':      _launch_standalone,
    'cannonball':  _launch_standalone,
    'catacombgl':  _launch_catacombgl,
    'cdogs':       _launch_standalone,
    'cgenius':     _launch_standalone,
    'corsixth':    _launch_corsixth,
    'demul':       launch_demul,
    'devilutionx': _launch_standalone,
    'dhewm3':      _launch_standalone,
    'dxx-rebirth': _launch_standalone,
    'ecwolf':      _launch_standalone,
    'eduke32':     _launch_eduke32,
    'fury':        _launch_eduke32,
    'etlegacy':    _launch_standalone,
    'fallout1-ce': _launch_fallout1_ce,
    'fallout2-ce': _launch_fallout2_ce,
    'flatpak':     _launch_flatpak,
    'clk':         _launch_clk,
    'easyrpg':     launch_easyrpg,
    'fsuae':       launch_fsuae,
    'gzdoom':      _launch_gzdoom,
    'hcl':         _launch_standalone,
    'hurrican':    _launch_standalone,
    'gsplus':      _launch_gsplus,
    'hypseus-singe': launch_hypseus_singe,
    'ikemen':      launch_ikemen,
    'iortcw':      _launch_standalone,
    'jazz2-native': _launch_standalone,
    'lightspark':  _launch_lightspark,
    'lindbergh-loader': _launch_lindbergh_loader,
    'model2emu':   _launch_model2emu,
    'moonlight':   _launch_standalone,
    'mugen':       _launch_standalone,
    'play':        _launch_play,
    'odcommander': _launch_standalone,
    'openjazz':    _launch_standalone,
    'openjk':      _launch_standalone,
    'openjkdf2':   _launch_standalone,
    'openmohaa':   _launch_standalone,
    'openbor':     _launch_openbor,
    'pyxel':       _launch_pyxel,
    'raze':        _launch_standalone,
    'pygame':      _launch_pygame,
    'ruffle':      _launch_ruffle,
    'ryujinx':     _launch_ryujinx,
    'samcoupe':    _launch_simcoupe,
    'sdlpop':      _launch_standalone,
    'solarus':     _launch_solarus,
    'sonic-mania': _launch_sonic_mania,
    'sonic2013':   _launch_sonicretro,
    'sonic3-air':  _launch_sonic3air,
    'soniccd':     _launch_sonicretro,
    'steam':       _launch_steam,
    'sugarbox':    launch_sugarbox,
    'supermodel':  _launch_supermodel,
    'taradino':    _launch_standalone,
    'theforceengine': _launch_theforceengine,
    'thextech':    launch_thextech,
    'tic80':       launch_tic80,
    'tr1x':        _launch_standalone,
    'tr2x':        _launch_tr2x,
    'tyrian':      _launch_standalone,
    'tsugaru':     _launch_tsugaru,
    'vpinball':    _launch_vpinball,
    'vkquake':     _launch_standalone,
    'vkquake2':    _launch_standalone,
    'vkquake3':    _launch_standalone,
    'wine':        _launch_wine,
    'x16emu':      _launch_x16emu,
    'xash3d_fwgs': _launch_standalone,
    'xroar':       launch_xroar,
    'ymir':        launch_ymir,
    'yquake2':     _launch_standalone,
    'fceux':       _launch_standalone,
    'hatari':      launch_hatari,
    'mame':        _launch_mame,
    'mednafen':    _launch_standalone,
    'mupen64plus': launch_mupen64plus,
    'mupen64plus-qt': _launch_mupen64plus_qt,
    'cemu':        _launch_cemu,
    'azahar':      _launch_azahar,
    'rpcs3':       _launch_rpcs3,
    'redream':     _launch_redream,
    'shadps4':     _launch_shadps4,
    'flycast':     _launch_flycast,
    'ppsspp':      _launch_ppsspp,
    'openmsx':     launch_openmsx,
    'scummvm':     launch_scummvm,
    'stella':      _launch_standalone,
    'vice':        _launch_vice,
    'vita3k':      _launch_vita3k,
    'melonds':     _launch_melonds,
    'basilisk2':   _launch_standalone,
    'desmume':     _launch_standalone,
    'nestopia':    _launch_standalone,
    'virtualjaguar': _launch_standalone,
    'xemu':        _launch_xemu,
    'ares':        _launch_ares,
    'xenia':       _launch_xenia,
    'xenia-canary': _launch_xenia,
    'xenia-edge':  launch_xenia_edge,
    'citron-neo':  launch_citron_neo,
    'eden':        launch_eden,
    'ioquake3':    _launch_ioquake3,
    'lexaloffle':  _launch_lexaloffle,
    'uqm':         _launch_uqm,
}


# ── Entry point ────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='HippOS emulator launcher')

    for n in range(1, 9):
        p.add_argument(f'-p{n}index',      type=int, required=False)
        p.add_argument(f'-p{n}guid',       type=str, required=False)
        p.add_argument(f'-p{n}name',       type=str, required=False)
        p.add_argument(f'-p{n}devicepath', type=str, required=False)
        p.add_argument(f'-p{n}iswheel',    type=int, required=False)
        p.add_argument(f'-p{n}wheelrotationangle', type=int, required=False)
        p.add_argument(f'-p{n}nbbuttons',  type=int, required=False)
        p.add_argument(f'-p{n}nbhats',     type=int, required=False)
        p.add_argument(f'-p{n}nbaxes',     type=int, required=False)

    p.add_argument('-system',       type=str,  required=True)
    p.add_argument('-rom',          type=Path, required=True)
    p.add_argument('-emulator',     type=str,  required=False)
    p.add_argument('-core',         type=str,  required=False)
    p.add_argument('-systemname',   type=str,  required=False)
    p.add_argument('-gameinfoxml',  type=str,  required=False, nargs='?', default=None, const=None)
    p.add_argument('-netplaymode',  type=str,  required=False)
    p.add_argument('-netplayip',    type=str,  required=False)
    p.add_argument('-netplayport',  type=str,  required=False)
    p.add_argument('-state_slot',   type=str,  required=False)
    p.add_argument('-state_filename', type=str, required=False)
    p.add_argument('-autosave',     type=str,  required=False)
    p.add_argument('-lightgun',     action='store_true')
    p.add_argument('-wheel',        action='store_true')
    return p


def _build_controllers(args: argparse.Namespace) -> list[ControllerInfo]:
    controllers = []
    for n in range(1, 9):
        idx = getattr(args, f'p{n}index', None)
        if idx is None:
            continue
        controllers.append(ControllerInfo(
            player=n,
            index=idx,
            guid=getattr(args, f'p{n}guid',       None) or '',
            name=getattr(args, f'p{n}name',       None) or '',
            device_path=getattr(args, f'p{n}devicepath', None) or '',
            is_wheel=bool(int(getattr(args, f'p{n}iswheel', 0) or 0)),
            wheel_rotation_angle=getattr(args, f'p{n}wheelrotationangle', None) or 0,
            nb_buttons=getattr(args, f'p{n}nbbuttons',  None) or 0,
            nb_hats=getattr(args, f'p{n}nbhats',     None) or 0,
            nb_axes=getattr(args, f'p{n}nbaxes',     None) or 0,
        ))
    return controllers


def main() -> int:
    args = _build_parser().parse_args()

    emulator, core = resolve_emulator_core(args.system, args.emulator, args.core, args.rom)
    controllers    = _build_controllers(args)

    ctx = LaunchContext(
        system=args.system,
        rom=args.rom,
        emulator=emulator,
        core=core,
        gameinfoxml=Path(args.gameinfoxml) if args.gameinfoxml and args.gameinfoxml != '/dev/null' else None,
        lightgun=args.lightgun,
        wheel=args.wheel,
        controllers=controllers,
    )
    ctx.rom         = _resolve_mergerfs_path(ctx.rom)
    ctx.game_wheel  = _load_game_wheel_metadata(ctx.gameinfoxml)
    ctx.game_gun    = _load_game_gun_metadata(ctx.gameinfoxml)
    ctx.netplay_mode = getattr(args, 'netplaymode', '') or ''
    ctx.netplay_ip   = getattr(args, 'netplayip',   '') or ''
    ctx.netplay_port = getattr(args, 'netplayport',  '') or ''

    _log.info("system=%s emulator=%s core=%s controllers=%d",
              ctx.system, ctx.emulator, ctx.core, len(ctx.controllers))

    conf = _load_hippos_conf()
    _apply_yaml_options(conf, ctx.system)
    if not _conf_bool(conf, 'global.use_guns', True):
        ctx.lightgun = False
    if not _conf_bool(conf, 'global.use_wheels', True):
        ctx.wheel = False

    if ctx.lightgun:
        os.environ['HIPPOS_LIGHTGUN'] = '1'
    else:
        os.environ.pop('HIPPOS_LIGHTGUN', None)
    if ctx.wheel:
        os.environ['HIPPOS_WHEEL'] = '1'
        for ctrl in ctx.controllers:
            if ctrl.is_wheel and ctrl.wheel_rotation_angle > 0:
                os.environ['HIPPOS_WHEEL_ROTATION_ANGLE'] = str(ctrl.wheel_rotation_angle)
                break
    else:
        os.environ.pop('HIPPOS_WHEEL', None)
        os.environ.pop('HIPPOS_WHEEL_ROTATION_ANGLE', None)

    generator = GENERATORS.get(ctx.emulator)
    if generator is None:
        _log.error("No generator registered for emulator '%s'", ctx.emulator)
        return 1

    profiles = _load_es_input_configs()
    start_controller_monitor(ctx, profiles)

    original_mode = _switch_video_mode(conf, ctx.system)
    raw_res = subprocess.run(
        ['hippos-resolution', 'currentResolution'],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    if m := re.match(r'(\d+)x(\d+)', raw_res):
        ctx.resolution = (int(m.group(1)), int(m.group(2)))
        _log.info("videomode: game resolution %dx%d", ctx.resolution[0], ctx.resolution[1])

    _prepare_ctx_bezel(ctx, conf)
    _build_hud_config(conf, ctx)

    power_governor = _apply_game_power_mode(conf, ctx.system, ctx.rom)
    try:
        return _run_with_squashfs(ctx, generator)
    finally:
        _restore_game_power_mode(power_governor)
        _restore_video_mode(original_mode, conf)


def _run_with_squashfs(ctx: LaunchContext, generator: Callable[[LaunchContext], int]) -> int:
    """Mount squashfs ROM if needed, apply overlayfs for saves, run generator."""
    if ctx.rom.suffix != '.squashfs':
        return generator(ctx)

    with mount_squashfs(ctx.rom) as squash_root:
        if ctx.emulator in WRITES_TO_ROM:
            saves_root = SAVES / ctx.system / ctx.rom.stem
            with mount_overlayfs(squash_root, saves_root) as overlay:
                ctx.rom = overlay
                return generator(ctx)
        else:
            ctx.rom = squash_root
            return generator(ctx)


if __name__ == '__main__':
    sys.exit(main())
