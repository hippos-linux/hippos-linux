"""Remaining emulator generators — all previously on _launch_standalone."""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from emulatorlauncher_impl import (
    BIOS, SAVES, CONFIGS, SCREENSHOTS, CACHE,
    LaunchContext,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _find_emulator_bin,
    _load_es_input_configs,
    _load_hippos_conf,
    _log,
    _pick_es_profile,
    _run_game_command,
    generate_sdl_game_controller_config,
)

# ── xenia-edge (native Linux build) ──────────────────────────────────────────
# xenia and xenia-canary run via Wine. xenia-edge is a native Linux binary —
# no Wine prefix, no z: path mangling, direct exec.

from emulatorlauncher_impl import (
    XENIA_SAVES_DIR, XENIA_CACHE_DIR,
    _load_effective_hippos_conf,
    _probe_vulkan_version,
    _conf_bool, _conf_int, _conf_value,
    _read_toml, _write_toml,
)
from emulatorlauncher_xenia import _xenia_base_config


def launch_xenia_edge(ctx: LaunchContext) -> int:
    conf = _load_effective_hippos_conf()

    cfg_dir = CONFIGS / 'xenia-edge'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    XENIA_SAVES_DIR.mkdir(parents=True, exist_ok=True)
    XENIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    toml_file = cfg_dir / 'xenia-edge.config.toml'
    config = _read_toml(toml_file) or _xenia_base_config(None)

    # GPU — prefer Vulkan on Linux native
    gpu = config.setdefault('GPU', {})
    gpu['gpu'] = _conf_value(conf, 'xenia_api', 'vulkan').lower()
    gpu['vsync'] = _conf_bool(conf, 'xenia_vsync', True)
    gpu['framerate_limit'] = _conf_int(conf, 'xenia_vsync_fps', 0)

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


# ── Switch emulators (citron-neo, eden) ────────────────────────────────────────

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

    # Bind Hotkey+Start (Home+Plus) to exit; clear fullscreen from that combo.
    # Set both the emu-specific name and the upstream yuzu name so forks that
    # haven't renamed the action still get the right binding.
    for action in (emu_name, 'yuzu'):
        exit_key = rf'Shortcuts\Main%20Window\Exit%20{action.replace("-", "%20")}\Controller_KeySeq'
        cfg.set('UI', exit_key, 'Home+Plus')
    cfg.set('UI', r'Shortcuts\Main%20Window\Fullscreen\Controller_KeySeq', '')

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    with cfg_file.open('w') as fh:
        cfg.write(fh)


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


# ── Ymir (Saturn) ──────────────────────────────────────────────────────────────

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

    # Write minimal TOML config for saves + screenshots
    cfg_file = cfg_dir / 'ymir.toml'
    if not cfg_file.exists():
        cfg_file.write_text(
            f'[paths]\n'
            f'saves = "{saves_dir}"\n'
            f'screenshots = "{SCREENSHOTS}"\n'
            f'bios = "{BIOS}"\n'
        )

    cmd = [
        str(bin_path),
        '--config', str(cfg_file),
        '--fullscreen',
        str(ctx.rom),
    ]
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    return _run_game_command(ctx, 'ymir', cmd, env).returncode


# ── XRoar (CoCo / Dragon) ──────────────────────────────────────────────────────

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


# ── EasyRPG ────────────────────────────────────────────────────────────────────

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


# ── TheXTech ───────────────────────────────────────────────────────────────────

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


# ── Hypseus-Singe (Daphne/Singe laserdisc) ────────────────────────────────────

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

    # Copy gamepad input config template if not already present
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


# ── TIC-80 ─────────────────────────────────────────────────────────────────────

def launch_tic80(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / ctx.system
    saves_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('tic80')
    if bin_path is None:
        _log.error("tic80: binary not found")
        return 1

    cmd = [str(bin_path), '--fullscreen', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'tic80', cmd, env).returncode


# ── Ikemen GO (M.U.G.E.N engine) ──────────────────────────────────────────────

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

    # Write config.json with Fullscreen + input config
    cfg_path = game_dir / 'save' / 'config.json'
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cfg = _json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    except Exception:
        cfg = {}

    # Build joystick mapping from connected controllers
    joymapping = [
        {'Joystick': ctrl.index, 'Buttons': ['Not used'] * 14}
        for ctrl in ctx.controllers[:4]
    ]
    # Pad to 4 slots
    while len(joymapping) < 4:
        joymapping.append({'Joystick': len(joymapping), 'Buttons': ['Not used'] * 14})

    cfg['KeyConfig']      = _IKEMEN_KEYMAPPING
    cfg['JoystickConfig'] = joymapping
    cfg['Fullscreen']     = True

    cfg_path.write_text(_json.dumps(cfg, indent=2))

    cmd = [str(bin_path), '-f']
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'ikemen', cmd, env, cwd=game_dir).returncode


# ── BigPEmu (Atari Jaguar) ────────────────────────────────────────────────────

# BigPEmu P1 binding sequence (es_name → bigpemu_action)
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

    # Preserve BIOS paths that BigPEmu writes itself
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
        'VSync': int(_conf_value(conf, 'bigpemu_vsync', '1')),
        'ScreenAspect': int(_conf_value(conf, 'bigpemu_ratio', '2')),
        'LockAspect': 1,
        'ScreenFilter': int(_conf_value(conf, 'bigpemu_screenfilter', '0')),
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


# ── AppleWin / QApple (Apple II) ──────────────────────────────────────────────

def launch_applewin(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    saves_dir = SAVES / ctx.system
    cfg_dir   = CONFIGS / 'applewin'
    saves_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('qapple', 'applewin')
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
    env['QT_QPA_PLATFORM'] = 'xcb'
    return _run_game_command(ctx, 'applewin', cmd, env).returncode


# ── Demul (Windows arcade emulator) ───────────────────────────────────────────

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
    return _run_game_command(ctx, 'demul', cmd, env).returncode


# ── Sugarbox (ZX Spectrum) ────────────────────────────────────────────────────

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

    cmd = [str(bin_path), '--fullscreen', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(cfg_dir)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    return _run_game_command(ctx, 'sugarbox', cmd, env).returncode
