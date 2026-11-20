from __future__ import annotations

import configparser
import filecmp
import json
import re
import shutil
import zipfile
from pathlib import Path

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _find_emulator_bin,
    _load_hippos_conf,
    _log,
    _run_game_command,
)
from emulatorlauncher_registry import Emulator, register

from HipposPaths import BIOS, CACHE, CONFIGS, SAVES, USERDATA

def _write_switch_qt_config(cfg_dir: Path, emu_name: str) -> None:
    cfg_file = cfg_dir / 'qt-config.ini'
    cfg = configparser.RawConfigParser()
    cfg.optionxform = str
    if cfg_file.exists():
        cfg.read(cfg_file)
    if not cfg.has_section('UI'):
        cfg.add_section('UI')

    cfg.set('UI', 'fullscreen', 'true')
    cfg.set('UI', r'fullscreen\default', 'false')
    cfg.set('UI', 'confirmStop', '2')
    cfg.set('UI', r'confirmStop\default', 'false')
    cfg.set('UI', 'firstStart', 'false')
    cfg.set('UI', r'firstStart\default', 'false')
    cfg.set('UI', 'enable_discord_presence', 'false')
    cfg.set('UI', r'enable_discord_presence\default', 'false')

    for action in (emu_name, 'yuzu'):
        exit_key = rf'Shortcuts\Main%20Window\Exit%20{action.replace("-", "%20")}\Controller_KeySeq'
        cfg.set('UI', exit_key, 'Home+Plus')
    cfg.set('UI', r'Shortcuts\Main%20Window\Fullscreen\Controller_KeySeq', '')

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    with cfg_file.open('w') as fh:
        cfg.write(fh)

SWITCH_BIOS = BIOS / 'switch'
SWITCH_KEY_FILES = ('prod.keys', 'title.keys')
SWITCH_DATA_DIRS = {'citron-neo': 'citron', 'eden': 'eden'}

def install_switch_keys(keys_dir: Path) -> None:
    keys_dir.mkdir(parents=True, exist_ok=True)
    for name in SWITCH_KEY_FILES:
        source, target = SWITCH_BIOS / 'keys' / name, keys_dir / name
        if source.is_file() and not (target.is_file() and filecmp.cmp(source, target, shallow=False)):
            shutil.copyfile(source, target)
            _log.info("Switch: installed %s", name)

def _version_key(path: Path) -> list[int]:
    return [int(part) for part in re.findall(r'\d+', path.stem)]

def switch_firmware() -> Path | None:
    folder = SWITCH_BIOS / 'firmware'
    if any(folder.glob('*.nca')):
        return folder
    archives = [*SWITCH_BIOS.glob('*.zip'), *folder.glob('*.zip')]
    return max(archives, key=_version_key) if archives else None

def _firmware_entry(name: str, title_folders: bool) -> str:
    return f"{name.split('.')[0]}.nca" if title_folders else name

def install_switch_firmware(registered: Path, title_folders: bool = False) -> None:
    source = switch_firmware()
    if source is None:
        return
    if source.is_dir():
        files = {path.name: (lambda path=path: path.open('rb')) for path in sorted(source.glob('*.nca'))}
        archive = None
    else:
        archive = zipfile.ZipFile(source)
        files = {Path(name).name: (lambda member=name: archive.open(member))
                 for name in archive.namelist() if name.lower().endswith('.nca')}
    try:
        registered.mkdir(parents=True, exist_ok=True)
        wanted = sorted(_firmware_entry(name, title_folders) for name in files)
        if sorted(path.name for path in registered.glob('*.nca')) == wanted:
            return
        for path in registered.glob('*.nca'):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        for name, open_source in files.items():
            target = registered / _firmware_entry(name, title_folders)
            if title_folders:
                target.mkdir()
                target = target / '00'
            with open_source() as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst)
        _log.info("Switch: installed firmware from %s", source)
    finally:
        if archive is not None:
            archive.close()

def _launch_switch(ctx: LaunchContext, emu_name: str) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / 'switch'
    cfg_dir   = CONFIGS / SWITCH_DATA_DIRS[emu_name]
    cache_dir = CACHE / emu_name
    saves_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin(emu_name)
    if bin_path is None:
        _log.error("%s: binary not found", emu_name)
        return 1

    _write_switch_qt_config(cfg_dir, emu_name)
    data_dir = saves_dir / SWITCH_DATA_DIRS[emu_name]
    install_switch_keys(data_dir / 'keys')
    install_switch_firmware(data_dir / 'nand' / 'system' / 'Contents' / 'registered')

    cmd = [str(bin_path), '-f', '-g', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_DATA_HOME']   = str(saves_dir)
    env['XDG_CACHE_HOME']  = str(cache_dir)
    env['QT_QPA_PLATFORM'] = 'xcb'
    return _run_game_command(ctx, cmd, env).returncode

def launch_citron_neo(ctx: LaunchContext) -> int:
    return _launch_switch(ctx, 'citron-neo')

def launch_eden(ctx: LaunchContext) -> int:
    return _launch_switch(ctx, 'eden')

_RYUJINX_CTRL_TEMPLATE: dict = {
    'left_joycon_stick':  {'joystick': 'Left', 'invert_stick_x': False, 'invert_stick_y': False, 'rotate90_cw': False, 'stick_button': 'LeftStick'},
    'right_joycon_stick': {'joystick': 'Right', 'invert_stick_x': False, 'invert_stick_y': False, 'rotate90_cw': False, 'stick_button': 'RightStick'},
    'deadzone_left': 0, 'deadzone_right': 0, 'range_left': 1, 'range_right': 1, 'trigger_threshold': 0,
    'motion': {'motion_backend': 'GamepadDriver', 'sensitivity': 100, 'gyro_deadzone': 1, 'enable_motion': True},
    'rumble': {'strong_rumble': 8.0, 'weak_rumble': 2.0, 'enable_rumble': True},
    'left_joycon': {
        'button_minus': 'Minus', 'button_l': 'LeftShoulder', 'button_zl': 'LeftTrigger',
        'button_sl': 'Unbound', 'button_sr': 'Unbound',
        'dpad_up': 'DpadUp', 'dpad_down': 'DpadDown', 'dpad_left': 'DpadLeft', 'dpad_right': 'DpadRight',
    },
    'right_joycon': {
        'button_plus': 'Plus', 'button_r': 'RightShoulder', 'button_zr': 'RightTrigger',
        'button_sl': 'Unbound', 'button_sr': 'Unbound',
        'button_x': 'Y', 'button_b': 'A', 'button_y': 'X', 'button_a': 'B',
    },
    'version': 1,
    'backend': 'GamepadSDL2',
}

def _ryujinx_ctrl_uuid(ctrl) -> str:
    guid = (ctrl.guid or '').lower().replace('-', '')
    if len(guid) == 32:
        bustype    = guid[0:8]
        vendor     = guid[8:12]
        product    = guid[16:20]
        version    = guid[24:28]
        prod_rev   = product[2:4] + product[0:2]
        ver_rev    = version[2:4] + version[0:2]
        return f'{ctrl.index}-{bustype}-{vendor}-0000-{prod_rev}-0000{ver_rev}0000'
    return f'{ctrl.index}-00000003-0000-0000-0000-000000000000'

def launch_ryujinx(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('Ryujinx.sh', 'Ryujinx', 'ryujinx')
    if bin_path is None:
        _log.error("ryujinx not installed")
        return 1
    cfg_path = USERDATA / 'system' / 'configs' / 'Ryujinx' / 'Config.json'
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            pass
    cfg['start_fullscreen'] = True
    cfg['docked_mode']      = True
    cfg['input_config']     = []

    for nplayer, ctrl in enumerate(ctx.controllers[:8], start=1):
        ctrl_cfg = dict(_RYUJINX_CTRL_TEMPLATE)
        ctrl_cfg['id']              = _ryujinx_ctrl_uuid(ctrl)
        ctrl_cfg['controller_type'] = 'ProController'
        ctrl_cfg['player_index']    = f'Player{nplayer}'
        cfg['input_config'].append(ctrl_cfg)

    cfg_path.write_text(json.dumps(cfg, indent=2))
    install_switch_keys(cfg_path.parent / 'system')
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    install_switch_firmware(cfg_path.parent / 'bis' / 'system' / 'Contents' / 'registered', title_folders=True)
    cmd = [str(bin_path), '--fullscreen', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

register(Emulator('ryujinx', launch_ryujinx, binaries=('Ryujinx.sh', 'Ryujinx', 'ryujinx')))
register(Emulator('citron-neo', launch_citron_neo, binaries=('citron-neo', 'citron')))
register(Emulator('eden', launch_eden, binaries=('eden',)))
