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

from HipposPaths import CONFIGS, SAVES


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

    parser = _new_ini_parser()
    if XEMU_CONFIG_FILE.exists():
        try:
            parser.read(XEMU_CONFIG_FILE, encoding='utf-8')
        except Exception:
            pass

    for section in ('general', 'sys', 'sys.files', 'audio', 'display', 'display.quality', 'display.vulkan', 'display.window', 'display.ui', 'input.bindings', 'net', 'net.udp'):
        if not parser.has_section(section):
            parser.add_section(section)

    parser.set('general', 'skip_boot_anim', _conf_value(conf, 'xemu_bootanim', 'false'))
    parser.set('general', 'show_welcome', 'false')
    parser.set('general', 'screenshot_dir', '"/userdata/screenshots"')

    parser.set('sys', 'mem_limit', f'"{_conf_value(conf, "xemu_memory", "64")}"')
    if ctx.system == 'chihiro':
        parser.set('sys', 'mem_limit', '"128"')
        parser.set('sys.files', 'flashrom_path', '"/userdata/bios/cerbios.bin"')
    else:
        parser.set('sys.files', 'flashrom_path', '"/userdata/bios/Complex_4627.bin"')

    parser.set('sys.files', 'bootrom_path', '"/userdata/bios/mcpx_1.0.bin"')
    parser.set('sys.files', 'hdd_path', '"/userdata/saves/xbox/xbox_hdd.qcow2"')
    parser.set('sys.files', 'eeprom_path', '"/userdata/saves/xbox/xemu_eeprom.bin"')
    parser.set('sys.files', 'dvd_path', f'"{ctx.rom}"')
    parser.set('audio', 'use_dsp', _conf_value(conf, 'xemu_use_dsp', 'false'))

    renderer = _conf_value(conf, 'xemu_api', 'VULKAN').upper()
    if ctx.system == 'chihiro':
        renderer = 'OPENGL'
    parser.set('display', 'renderer', f'"{renderer}"')
    if renderer == 'VULKAN':
        device_name = _xemu_vulkan_device_name()
        parser.set('display.vulkan', 'preferred_physical_device', f'"{device_name}"' if device_name else '""')

    parser.set('display.quality', 'surface_scale', _conf_value(conf, 'xemu_render', '1'))
    parser.set('display.window', 'fullscreen_on_startup', 'true')
    display_resolution = _display_resolution_from_conf(conf) or (1280, 720)
    parser.set('display.window', 'startup_size', f'"{display_resolution[0]}x{display_resolution[1]}"')
    parser.set('display.window', 'vsync', _conf_value(conf, 'xemu_vsync', 'true'))
    parser.set('display.ui', 'show_menubar', 'false')
    parser.set('display.ui', 'fit', f'"{_conf_value(conf, "xemu_scaling", "scale")}"')
    parser.set('display.ui', 'aspect_ratio', f'"{_conf_value(conf, "xemu_aspect", "auto")}"')

    for idx in range(1, 5):
        parser.remove_option('input.bindings', f'port{idx}')
    for nplayer, pad in enumerate(ctx.controllers[:4], start=1):
        parser.set('input.bindings', f'port{nplayer}', f'"{pad.guid}"')

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


XEMU_CONFIG_DIR = CONFIGS / 'xemu'
XEMU_CONFIG_FILE = XEMU_CONFIG_DIR / 'xemu.toml'
XEMU_SAVES_DIR = SAVES / 'xbox'
XEMU_DATA_DIRS = (Path('/opt/emulators/xemu/data'), Path('/usr/share/xemu/data'))
