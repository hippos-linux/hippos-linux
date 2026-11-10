from __future__ import annotations

import re
import subprocess
from pathlib import Path
from shutil import copyfile
from typing import Optional

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_value,
    _display_resolution_from_conf,
    _find_emulator_bin,
    _load_hippos_conf,
    _new_ini_parser,
    _run_game_command,
)

from HipposPaths import BIOS, CONFIGS, SAVES

def _xemu_find_data_dir() -> Optional[Path]:
    for data_dir in XEMU_DATA_DIRS:
        if (data_dir / 'xbox_hdd.qcow2').exists():
            return data_dir
    return None

def _xemu_vulkan_device_name() -> Optional[str]:
    from shutil import which

    vulkaninfo = which('vulkaninfo')
    if vulkaninfo is None:
        return None
    try:
        proc = subprocess.run([vulkaninfo, '--summary'], capture_output=True, text=True, timeout=5, check=False)
    except Exception:
        return None
    output = '\n'.join(part for part in (proc.stdout, proc.stderr) if part)
    match = re.search(r'deviceName\s*=\s*([^\n]+)', output, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip('"')
    match = re.search(r'GPU id\s+\d+\s*:\s*([^\n]+)', output, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip('"')
    return None

def _read_xemu_toml(config_file: Path, sections: tuple[str, ...]):
    parser = _new_ini_parser()
    if config_file.exists():
        try:
            parser.read(config_file, encoding='utf-8')
        except Exception:
            pass
    for section in sections:
        if not parser.has_section(section):
            parser.add_section(section)
    return parser

def _set_xemu_display(parser, conf: dict[str, str], prefix: str, default_renderer: str) -> None:
    renderer = _conf_value(conf, f'{prefix}_api', default_renderer).upper()
    parser.set('display', 'renderer', f'"{renderer}"')
    if renderer == 'VULKAN':
        device_name = _xemu_vulkan_device_name()
        parser.set('display.vulkan', 'preferred_physical_device', f'"{device_name}"' if device_name else '""')

    parser.set('display.quality', 'surface_scale', _conf_value(conf, f'{prefix}_render', '1'))
    parser.set('display.window', 'fullscreen_on_startup', 'true')
    display_resolution = _display_resolution_from_conf(conf) or (1280, 720)
    parser.set('display.window', 'startup_size', f'"{display_resolution[0]}x{display_resolution[1]}"')
    parser.set('display.window', 'vsync', _conf_value(conf, f'{prefix}_vsync', 'true'))
    parser.set('display.ui', 'show_menubar', 'false')
    parser.set('display.ui', 'fit', f'"{_conf_value(conf, f"{prefix}_scaling", "scale")}"')
    parser.set('display.ui', 'aspect_ratio', f'"{_conf_value(conf, f"{prefix}_aspect", "auto")}"')

def _set_xemu_bindings(parser, ctx: LaunchContext) -> None:
    for idx in range(1, 5):
        parser.remove_option('input.bindings', f'port{idx}')
    for nplayer, pad in enumerate(ctx.controllers[:4], start=1):
        parser.set('input.bindings', f'port{nplayer}', f'"{pad.guid}"')

XEMU_DISPLAY_SECTIONS = ('display', 'display.quality', 'display.vulkan', 'display.window', 'display.ui', 'input.bindings')

def write_xemu_config(ctx: LaunchContext) -> None:
    conf = _load_hippos_conf()
    XEMU_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    XEMU_SAVES_DIR.mkdir(parents=True, exist_ok=True)

    data_dir = _xemu_find_data_dir()
    if data_dir is not None:
        hdd_src = data_dir / 'xbox_hdd.qcow2'
        hdd_dst = XEMU_SAVES_DIR / 'xbox_hdd.qcow2'
        if not hdd_dst.exists():
            copyfile(hdd_src, hdd_dst)

    parser = _read_xemu_toml(XEMU_CONFIG_FILE, ('general', 'sys', 'sys.files', 'audio', 'net', 'net.udp') + XEMU_DISPLAY_SECTIONS)

    parser.set('general', 'skip_boot_anim', _conf_value(conf, 'xemu_bootanim', 'false'))
    parser.set('general', 'show_welcome', 'false')
    parser.set('general', 'screenshot_dir', '"/userdata/screenshots"')

    parser.set('sys', 'mem_limit', f'"{_conf_value(conf, "xemu_memory", "64")}"')
    parser.set('sys.files', 'flashrom_path', '"/userdata/bios/Complex_4627.bin"')
    parser.set('sys.files', 'bootrom_path', '"/userdata/bios/mcpx_1.0.bin"')
    parser.set('sys.files', 'hdd_path', '"/userdata/saves/xbox/xbox_hdd.qcow2"')
    parser.set('sys.files', 'eeprom_path', '"/userdata/saves/xbox/xemu_eeprom.bin"')
    parser.set('sys.files', 'dvd_path', f'"{ctx.rom}"')
    parser.set('audio', 'use_dsp', _conf_value(conf, 'xemu_use_dsp', 'false'))

    _set_xemu_display(parser, conf, 'xemu', 'VULKAN')
    _set_xemu_bindings(parser, ctx)

    network_type = _conf_value(conf, 'xemu_networktype', '')
    if network_type:
        parser.set('net', 'enable', 'true')
        parser.set('net', 'backend', f'"{network_type}"')
    else:
        parser.set('net', 'enable', 'false')
    if udpremote := _conf_value(conf, 'xemu_udpremote', ''):
        parser.set('net.udp', 'remote_addr', f'"{udpremote}"')
    if udpbind := _conf_value(conf, 'xemu_udpbind', ''):
        parser.set('net.udp', 'bind_addr', f'"{udpbind}"')

    with XEMU_CONFIG_FILE.open('w', encoding='utf-8') as fh:
        parser.write(fh)

def write_xemu_chihiro_config(ctx: LaunchContext) -> None:
    conf = _load_hippos_conf()
    CHIHIRO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CHIHIRO_SAVES_DIR.mkdir(parents=True, exist_ok=True)

    parser = _read_xemu_toml(CHIHIRO_CONFIG_FILE, ('general', 'general.updates', 'sys', 'sys.files', 'audio',
                                                    'chihiro.roms', 'chihiro.settings') + XEMU_DISPLAY_SECTIONS)

    parser.set('general', 'show_welcome', 'false')
    parser.set('general', 'screenshot_dir', '"/userdata/screenshots"')
    parser.set('general.updates', 'check', 'false')

    parser.set('sys', 'default_machine', '"chihiro"')
    parser.set('sys.files', 'dvd_path', f'"{ctx.rom}"')
    parser.set('audio', 'use_dsp', _conf_value(conf, 'xemu_chihiro_use_dsp', 'false'))

    parser.set('chihiro.roms', 'bios_path', f'"{CHIHIRO_BIOS_DIR / "chihiro_xbox_bios.bin"}"')
    net_firmware = CHIHIRO_BIOS_DIR / 'ver1305.bin'
    parser.set('chihiro.roms', 'net_firmware_path', f'"{net_firmware}"' if net_firmware.is_file() else '""')
    parser.set('chihiro.settings', 'region', f'"{_conf_value(conf, "xemu_chihiro_region", "ex")}"')
    parser.set('chihiro.settings', 'freeplay', _conf_value(conf, 'xemu_chihiro_freeplay', 'false'))

    _set_xemu_display(parser, conf, 'xemu_chihiro', 'OPENGL')
    _set_xemu_bindings(parser, ctx)

    with CHIHIRO_CONFIG_FILE.open('w', encoding='utf-8') as fh:
        parser.write(fh)

def launch_xemu(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('xemu')
    if bin_path is None:
        return 1
    write_xemu_config(ctx)
    conf = _load_hippos_conf()
    cmd = [str(bin_path), '-config_path', str(XEMU_CONFIG_FILE)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['SDL_GAMECONTROLLERCONFIG'] = ''
    env['LC_NUMERIC'] = 'C'
    result = _run_game_command(ctx, 'xemu', cmd, env)
    return result.returncode

def launch_xemu_chihiro(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('xemu-chihiro')
    if bin_path is None:
        return 1
    write_xemu_chihiro_config(ctx)
    conf = _load_hippos_conf()
    cmd = [str(bin_path), '-config_path', str(CHIHIRO_CONFIG_FILE)]
    env = _build_game_env(conf, ctx)
    env['XDG_DATA_HOME'] = str(CHIHIRO_SAVES_DIR)
    env['SDL_GAMECONTROLLERCONFIG'] = ''
    env['LC_NUMERIC'] = 'C'
    result = _run_game_command(ctx, 'xemu-chihiro', cmd, env)
    return result.returncode

XEMU_CONFIG_DIR = CONFIGS / 'xemu'
XEMU_CONFIG_FILE = XEMU_CONFIG_DIR / 'xemu.toml'
XEMU_SAVES_DIR = SAVES / 'xbox'
XEMU_DATA_DIRS = (Path('/opt/emulators/xemu/data'), Path('/usr/share/xemu/data'))
CHIHIRO_CONFIG_DIR = CONFIGS / 'xemu-chihiro'
CHIHIRO_CONFIG_FILE = CHIHIRO_CONFIG_DIR / 'xemu.toml'
CHIHIRO_SAVES_DIR = SAVES / 'chihiro'
CHIHIRO_BIOS_DIR = BIOS / 'chihiro'
