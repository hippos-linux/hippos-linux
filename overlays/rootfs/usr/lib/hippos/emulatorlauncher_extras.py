
from __future__ import annotations

import configparser
import filecmp
import shutil
from pathlib import Path

from emulatorlauncher_shared import (
    _game_bool,
    _game_int,
    _game_value,
    WINE_NO_INSTALLER_PROMPTS,
    LaunchContext,
    _build_game_env,
    _conf_value,
    _ensure_section,
    _find_emulator_bin,
    _load_es_input_configs,
    _load_hippos_conf,
    _log,
    _new_ini_parser,
    _pick_es_profile,
    _run_game_command,
    generate_sdl_game_controller_config,
)

from HipposPaths import BIOS, CACHE, CONFIGS, SAVES, SCREENSHOTS

from emulatorlauncher_shared import (
    _conf_value,
    _load_effective_hippos_conf,
    _read_toml,
    _write_toml,
)
from emulatorlauncher_xenia import XENIA_CACHE_DIR, XENIA_SAVES_DIR, _xenia_base_config

def launch_xenia_edge(ctx: LaunchContext) -> int:
    conf = _load_effective_hippos_conf()

    cfg_dir = CONFIGS / 'xenia-edge'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    XENIA_SAVES_DIR.mkdir(parents=True, exist_ok=True)
    XENIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    toml_file = cfg_dir / 'xenia-edge.config.toml'
    config = _read_toml(toml_file) or _xenia_base_config(None)

    gpu = config.setdefault('GPU', {})
    gpu['gpu'] = _game_value(conf, ctx, 'xenia_api', 'vulkan').lower()
    gpu['vsync'] = _game_bool(conf, ctx, 'xenia_vsync', True)
    gpu['framerate_limit'] = _game_int(conf, ctx, 'xenia_vsync_fps', 0)

    storage = config.setdefault('Storage', {})
    storage['cache_root']   = str(XENIA_CACHE_DIR)
    storage['content_root'] = str(XENIA_SAVES_DIR)
    storage['storage_root'] = str(cfg_dir)
    storage['mount_cache']  = True

    config.setdefault('Display', {})['fullscreen'] = True
    config.setdefault('HID', {})['hid'] = 'sdl'
    config.setdefault('General', {})['discord'] = False
    config.setdefault('Logging', {})['log_level'] = 1

    _write_toml(toml_file, config)

    bin_path = _find_emulator_bin('xenia-edge')
    if bin_path is None:
        _log.error("xenia-edge: binary not found")
        return 1

    rom = ctx.rom
    if rom.suffix == '.xbox360':
        try:
            first = rom.read_text(encoding='utf-8').splitlines()[0].strip().lstrip('/')
            candidate = rom.parent / first
            if candidate.exists():
                rom = candidate
        except Exception:
            pass

    cmd = [str(bin_path), str(rom)]

    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    env['VKD3D_SHADER_CACHE_PATH'] = str(XENIA_CACHE_DIR)

    return _run_game_command(ctx, 'xenia-edge', cmd, env, cwd=cfg_dir).returncode

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
    cfg.set('UI', 'confirmClose', 'false')
    cfg.set('UI', r'confirmClose\default', 'false')
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

def _install_switch_keys(data_dir: Path) -> None:
    keys_dir = data_dir / 'keys'
    keys_dir.mkdir(parents=True, exist_ok=True)
    for name in SWITCH_KEY_FILES:
        source, target = SWITCH_BIOS / 'keys' / name, keys_dir / name
        if source.is_file() and not (target.is_file() and filecmp.cmp(source, target, shallow=False)):
            shutil.copyfile(source, target)
            _log.info("Switch: installed %s", name)

def _install_switch_firmware(data_dir: Path) -> None:
    firmware = sorted((SWITCH_BIOS / 'firmware').glob('*.nca'))
    if not firmware:
        return
    registered = data_dir / 'nand' / 'system' / 'Contents' / 'registered'
    registered.mkdir(parents=True, exist_ok=True)
    installed = sorted(registered.glob('*.nca'))
    if [path.name for path in installed] == [path.name for path in firmware]:
        return
    for path in installed:
        path.unlink()
    for path in firmware:
        shutil.copyfile(path, registered / path.name)
    _log.info("Switch: installed %d firmware files", len(firmware))

def _launch_switch(ctx: LaunchContext, emu_name: str) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / 'switch'
    cfg_dir   = CONFIGS / emu_name
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
    _install_switch_keys(data_dir)
    _install_switch_firmware(data_dir)

    cmd = [str(bin_path), '-f', '-g', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_DATA_HOME']   = str(saves_dir)
    env['XDG_CACHE_HOME']  = str(cache_dir)
    env['QT_QPA_PLATFORM'] = 'xcb'
    return _run_game_command(ctx, emu_name, cmd, env).returncode

def launch_citron_neo(ctx: LaunchContext) -> int:
    return _launch_switch(ctx, 'citron-neo')

def launch_eden(ctx: LaunchContext) -> int:
    return _launch_switch(ctx, 'eden')

def launch_ymir(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / ctx.system
    cfg_dir   = CONFIGS / 'ymir'
    saves_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('ymir')
    if bin_path is None:
        _log.error("ymir: binary not found")
        return 1

    cfg_file = cfg_dir / 'Ymir.toml'
    if not cfg_file.exists():
        cfg_file.write_text(
            f"[General.PathOverrides]\n"
            f"BackupMemory = '{saves_dir}'\n"
            f"IPLROMImages = '{BIOS}'\n"
            f"Screenshots = '{SCREENSHOTS}'\n"
        )

    cmd = [str(bin_path), '--profile', str(cfg_dir), '--fullscreen', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    return _run_game_command(ctx, 'ymir', cmd, env).returncode

_XROAR_MACHINES = {
    'coco':     'coco2bus',
    'dragon64': 'dragon64',
    'mc10':     'mc10',
}

def launch_xroar(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / ctx.system
    cfg_dir   = CONFIGS / 'xroar'
    saves_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('xroar')
    if bin_path is None:
        _log.error("xroar: binary not found")
        return 1

    machine = _conf_value(conf, 'xroar.machine',
                          _XROAR_MACHINES.get(ctx.system, 'coco2bus'))

    conf_file = cfg_dir / 'xroar.conf'
    with conf_file.open('w') as f:
        f.write(f'rompath {BIOS}/xroar\n')
        f.write(f'default-machine {machine}\n')
        f.write('ao-volume 100\n')
        f.write('fs\n')

    cmd = [str(bin_path), '-C', str(conf_file), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    return _run_game_command(ctx, 'xroar', cmd, env).returncode

def launch_easyrpg(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    rom = ctx.rom
    save_dir = SAVES / 'easyrpg' / rom.name
    cfg_dir  = CONFIGS / 'easyrpg'
    save_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('easyrpg-player', 'easyrpg')
    if bin_path is None:
        _log.error("easyrpg: binary not found")
        return 1

    encoding = _conf_value(conf, f'{ctx.system}.encoding', 'auto')
    cmd = [
        str(bin_path),
        '--encoding',     encoding,
        '--save-path',    str(save_dir),
        '--project-path', str(rom),
        '--fullscreen',
    ]
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'easyrpg', cmd, env).returncode

def launch_thextech(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / 'thextech'
    saves_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('thextech')
    if bin_path is None:
        _log.error("thextech: binary not found")
        return 1

    cmd = [str(bin_path), '-u', str(saves_dir), '-c', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'thextech', cmd, env).returncode

_HYPSEUS_SHARE_DIR = Path('/usr/share/hypseus-singe')
_DAPHNE_ROM_DIR    = BIOS / 'daphne'
_SINGE_ROM_DIR     = BIOS / 'singe'

def launch_hypseus_singe(ctx: LaunchContext) -> int:
    import shutil as _shutil
    conf    = _load_hippos_conf()
    rom     = ctx.rom
    cfg_dir = CONFIGS / 'hypseus-singe'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('hypseus', 'hypseus-singe')
    if bin_path is None:
        _log.error("hypseus-singe: binary not found")
        return 1

    gamepad_ini = _HYPSEUS_SHARE_DIR / 'hypinput_gamepad.ini'
    target_ini  = cfg_dir / 'hypinput.ini'
    if gamepad_ini.exists() and not target_ini.exists():
        _shutil.copyfile(gamepad_ini, target_ini)
    custom_ini = cfg_dir / 'custom.ini'
    if target_ini.exists() and not custom_ini.exists():
        _shutil.copyfile(target_ini, custom_ini)

    rom_dir  = rom if rom.is_dir() else rom.parent
    rom_name = rom_dir.name
    txt_file = next(rom_dir.glob('*.txt'), None)
    singe_file = rom_dir / f'{rom_name}.singe'
    zip_file   = rom_dir / f'{rom_name}.zip'

    keymapfile = 'custom.ini' if custom_ini.exists() else (target_ini.name if target_ini.exists() else None)

    is_singe = ctx.system == 'singe' or singe_file.exists() or zip_file.exists()

    if is_singe:
        if zip_file.exists():
            cmd = [str(bin_path), 'singe', 'vldp', '-retropath',
                   '-framefile', str(txt_file), '-zlua', str(zip_file)]
        else:
            cmd = [str(bin_path), 'singe', 'vldp', '-retropath',
                   '-framefile', str(txt_file), '-script', str(singe_file)]
        cmd += ['-fullscreen', '-gamepad',
                '-datadir', str(cfg_dir), '-singedir', str(_SINGE_ROM_DIR),
                '-romdir', str(_SINGE_ROM_DIR), '-homedir', str(cfg_dir)]
    else:
        cmd = [str(bin_path), rom_name, 'vldp',
               '-framefile', str(txt_file),
               '-fullscreen', '-fastboot', '-gamepad',
               '-datadir', str(cfg_dir), '-romdir', str(_DAPHNE_ROM_DIR),
               '-homedir', str(cfg_dir)]

    if keymapfile:
        cmd += ['-keymapfile', keymapfile]

    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'hypseus-singe', cmd, env, cwd=cfg_dir).returncode

def launch_tic80(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / ctx.system
    saves_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('tic80')
    if bin_path is None:
        _log.error("tic80: binary not found")
        return 1

    cmd = [str(bin_path), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'tic80', cmd, env).returncode

_IKEMEN_KEYMAPPING = [
    {'Joystick': -1, 'Buttons': ['UP','DOWN','LEFT','RIGHT','a','s','d','z','x','c','RETURN','f','v','q']},
    {'Joystick': -1, 'Buttons': ['KP_8','KP_5','KP_4','KP_6','p','LBRACKET','RBRACKET','SEMICOLON','QUOTE','BACKSLASH','SLASH','o','l','PERIOD']},
    {'Joystick': -1, 'Buttons': ['Not used']*14},
    {'Joystick': -1, 'Buttons': ['Not used']*14},
]

def launch_ikemen(ctx: LaunchContext) -> int:
    import json as _json
    conf = _load_hippos_conf()
    rom  = ctx.rom
    game_dir = rom if rom.is_dir() else rom.parent

    bin_path = _find_emulator_bin('Ikemen_GO', 'ikemen')
    if bin_path is None:
        _log.error("ikemen: binary not found")
        return 1

    cfg_path = game_dir / 'save' / 'config.json'
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cfg = _json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    except Exception:
        cfg = {}

    joymapping = [
        {'Joystick': ctrl.index, 'Buttons': ['Not used'] * 14}
        for ctrl in ctx.controllers[:4]
    ]
    while len(joymapping) < 4:
        joymapping.append({'Joystick': len(joymapping), 'Buttons': ['Not used'] * 14})

    cfg['KeyConfig']      = _IKEMEN_KEYMAPPING
    cfg['JoystickConfig'] = joymapping
    cfg['Fullscreen']     = True

    cfg_path.write_text(_json.dumps(cfg, indent=2))

    cmd = [str(bin_path), '-f']
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'ikemen', cmd, env, cwd=game_dir).returncode

_BIGPEMU_P1_BTNS: list[tuple[str, str]] = [
    ('y', 'C'), ('b', 'B'), ('a', 'A'), ('select', 'Pause'), ('start', 'Option'),
    ('up', 'Pad-Up'), ('down', 'Pad-Down'), ('left', 'Pad-Left'), ('right', 'Pad-Right'),
    ('pageup', 'Numpad-4'), ('x', 'Numpad-5'), ('pagedown', 'Numpad-6'),
    ('l3', 'Asterick'), ('r3', 'Pound'),
    ('joystick1left', 'Analog-0-left'), ('joystick1up', 'Analog-0-up'),
    ('joystick2left', 'Analog-1-left'), ('joystick2up', 'Analog-1-up'),
]
_BIGPEMU_AXIS_IDS: dict[str, int] = {
    'joystick1left': 128, 'joystick1up': 129, 'joystick2left': 131, 'joystick2up': 132,
}

def _bigpemu_binding(guid: str, input_id: int, input_type: str, value: float = 0.0) -> dict:
    return {'DeviceGuid': guid, 'InputID': input_id, 'InputType': input_type, 'Value': value}

def launch_bigpemu(ctx: LaunchContext) -> int:
    import json as _json
    conf      = _load_hippos_conf()
    profiles  = _load_es_input_configs()
    saves_dir = SAVES / ctx.system
    cfg_dir   = CONFIGS / 'bigpemu'
    saves_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('bigpemu')
    if bin_path is None:
        _log.error("bigpemu: binary not found")
        return 1

    cfg_file = cfg_dir / 'BigPEmuConfig.bigpcfg'

    preserved: dict = {}
    if cfg_file.exists():
        try:
            existing = _json.loads(cfg_file.read_text())
            for k in ('BootROM', 'CDBIOS', 'ScreenEffect'):
                if k in existing.get('BigPEmuConfig', {}):
                    preserved[k] = existing['BigPEmuConfig'][k]
        except Exception:
            pass
        cfg_file.unlink(missing_ok=True)

    w, h = ctx.resolution if ctx.resolution else (1920, 1080)

    cfg: dict = {'BigPEmuConfig': {}}
    cfg['BigPEmuConfig']['Video'] = {
        'DisplayMode': 2, 'ScreenScaling': 5,
        'DisplayWidth': w, 'DisplayHeight': h,
        'VSync': int(_game_value(conf, ctx, 'bigpemu_vsync', '1')),
        'ScreenAspect': int(_game_value(conf, ctx, 'bigpemu_ratio', '2')),
        'LockAspect': 1,
        'ScreenFilter': int(_game_value(conf, ctx, 'bigpemu_screenfilter', '0')),
    }

    inp: dict = {
        'DeviceCount': len(ctx.controllers),
        'AnalDeadMice': 0.25, 'AnalToDigi': 0.25, 'AnalExpo': 0.0,
        'InputVer': 2, 'InputPluginVer': 666,
    }
    for nplayer, ctrl in enumerate(ctx.controllers[:8]):
        profile  = _pick_es_profile(profiles, ctrl)
        bindings: list[dict] = []
        device: dict = {
            'DeviceType': 0, 'InvertAnally': 0,
            'RotaryScale': 0.5, 'HeadTrackerScale': 8.0,
            'HeadTrackerSpring': 0, 'Bindings': bindings,
        }
        inp[f'Device{nplayer}'] = device

        if profile:
            for es_name, _ in _BIGPEMU_P1_BTNS:
                binding = profile.inputs.get(es_name)
                if binding is None:
                    bindings.append({})
                    if es_name.startswith(('joystick1', 'joystick2')):
                        bindings.append({})
                    continue
                raw_id = _BIGPEMU_AXIS_IDS.get(es_name, binding.code)
                if es_name.startswith(('joystick1', 'joystick2')):
                    bindings.append(_bigpemu_binding(ctrl.guid, raw_id, 'axis', 1.0))
                    bindings.append(_bigpemu_binding(ctrl.guid, raw_id, 'axis', -1.0))
                else:
                    bindings.append(_bigpemu_binding(ctrl.guid, binding.code,
                                                     'button' if binding.type == 'button' else 'axis'))

    cfg['BigPEmuConfig']['Input'] = inp
    cfg['BigPEmuConfig']['ScriptsEnabled'] = []
    cfg['BigPEmuConfig']['ScriptSettings'] = {}
    cfg['BigPEmuConfig'].update(preserved)

    cfg_file.write_text(_json.dumps(cfg, indent=4))

    cmd = [str(bin_path), str(ctx.rom), '-cfgpathabs', str(cfg_file)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(cfg_dir)
    env['XDG_DATA_HOME']   = str(saves_dir)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    return _run_game_command(ctx, 'bigpemu', cmd, env).returncode

def launch_snes9x(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('snes9x')
    if bin_path is None:
        _log.error("snes9x: binary not found")
        return 1

    cfg_file = CONFIGS / 'snes9x' / 'snes9x-qt.conf'
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    parser = _new_ini_parser()
    if cfg_file.exists():
        parser.read(cfg_file)
    _ensure_section(parser, '%General')
    parser.set('%General', 'FullscreenOnOpen', 'true')
    with cfg_file.open('w') as f:
        parser.write(f, space_around_delimiters=False)

    conf = _load_effective_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['QT_QPA_PLATFORM'] = 'xcb'
    return _run_game_command(ctx, 'snes9x', [str(bin_path), str(ctx.rom)], env).returncode

def launch_nanoboyadvance(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('nanoboyadvance')
    if bin_path is None:
        _log.error("nanoboyadvance: binary not found")
        return 1

    conf = _load_effective_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['QT_QPA_PLATFORM'] = 'xcb'
    return _run_game_command(ctx, 'nanoboyadvance', [str(bin_path), str(ctx.rom)], env).returncode

def launch_sm2emu(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('sm2-emu')
    if bin_path is None:
        _log.error("sm2-emu: binary not found")
        return 1

    conf = _load_effective_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(
        ctx, 'sm2-emu',
        [str(bin_path), '--graphics-backend', 'opengl', str(ctx.rom)],
        env,
    ).returncode

def launch_eka2l1(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('eka2l1')
    if bin_path is None:
        _log.error("eka2l1: binary not found")
        return 1

    cmd = [str(bin_path), '--fullscreen']
    if ctx.rom.suffix.lower() in ('.sis', '.sisx'):
        cmd += ['--install', str(ctx.rom)]
    else:
        cmd += ['--mount', str(ctx.rom), '--runng']

    conf = _load_effective_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['XDG_DATA_HOME'] = str(CONFIGS)
    env['QT_QPA_PLATFORM'] = 'xcb'
    return _run_game_command(ctx, 'eka2l1', cmd, env).returncode

def launch_applewin(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / ctx.system
    cfg_dir   = CONFIGS / 'applewin'
    saves_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('applewin')
    if bin_path is None:
        _log.error("applewin: binary not found")
        return 1

    ext = ctx.rom.suffix.lower()
    cmd = [str(bin_path)]
    if ext in ('.dsk', '.do', '.po', '.nib', '.woz', '.2mg'):
        cmd += ['-1', str(ctx.rom)]
    else:
        cmd.append(str(ctx.rom))

    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(cfg_dir)
    return _run_game_command(ctx, 'applewin', cmd, env).returncode

_DEMUL_SYSTEMS = {
    'hikaru':  'hikaru',
    'gaelco':  'gaelco',
    'cave3rd': 'cavesh3',
}

def launch_demul(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / ctx.system
    cfg_dir   = CONFIGS / 'demul'
    saves_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('demul')
    if bin_path is None:
        _log.error("demul: binary not found")
        return 1

    gpu = _demul_system = _DEMUL_SYSTEMS.get(ctx.system, ctx.system)
    cmd = [
        str(bin_path),
        f'-run={_demul_system}',
        f'-rom={ctx.rom.stem}',
    ]

    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    env['WINEDLLOVERRIDES'] = WINE_NO_INSTALLER_PROMPTS
    return _run_game_command(ctx, 'demul', cmd, env).returncode

def launch_sugarbox(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / ctx.system
    cfg_dir   = CONFIGS / 'sugarbox'
    saves_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('SugarboxV2', 'sugarbox')
    if bin_path is None:
        _log.error("sugarbox: binary not found")
        return 1

    if ctx.rom.suffix.lower() != '.cpr':
        _log.error("sugarbox: only .cpr cartridges can be started directly: %s", ctx.rom)
        return 1
    cmd = [str(bin_path), '--cart', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(cfg_dir)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    return _run_game_command(ctx, 'sugarbox', cmd, env).returncode
