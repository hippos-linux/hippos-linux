from __future__ import annotations

import configparser
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _ensure_section,
    _find_emulator_bin,
    _load_hippos_conf,
    _log,
    _new_ini_parser,
    _run_game_command,
    generate_sdl_game_controller_config,
)

from HipposPaths import BIOS, CACHE, CONFIGS, SAVES, SCREENSHOTS, USERDATA

@dataclass(frozen=True)
class Pcsx2Flavor:
    name: str
    config_dir: Path
    bios_dirs: tuple[Path, ...]
    memcard_dir: Path
    cache_dir: Path

    @property
    def ini(self) -> Path:
        return self.config_dir / 'inis' / 'PCSX2.ini'

PCSX2 = Pcsx2Flavor(
    name='pcsx2',
    config_dir=CONFIGS / 'PCSX2',
    bios_dirs=(BIOS / 'ps2', BIOS),
    memcard_dir=SAVES / 'ps2' / 'pcsx2',
    cache_dir=CACHE / 'ps2',
)

ARMSX2 = Pcsx2Flavor(
    name='armsx2',
    config_dir=CONFIGS / 'ARMSX2',
    bios_dirs=(BIOS / 'ps2', BIOS),
    memcard_dir=SAVES / 'ps2' / 'armsx2',
    cache_dir=CACHE / 'ps2',
)

PCSX2X6 = Pcsx2Flavor(
    name='pcsx2x6',
    config_dir=CONFIGS / 'PCSX2x6',
    bios_dirs=(BIOS / 'namco2x6',),
    memcard_dir=SAVES / 'namco2x6' / 'pcsx2x6',
    cache_dir=CACHE / 'namco2x6',
)

def _write_pcsx2_config(flavor: Pcsx2Flavor, bios_dir: Path, conf: dict[str, str],
                        ctx: Optional['LaunchContext'] = None, bios_file: Optional[str] = None) -> None:
    flavor.ini.parent.mkdir(parents=True, exist_ok=True)
    (flavor.memcard_dir / 'sstates').mkdir(parents=True, exist_ok=True)
    flavor.cache_dir.mkdir(parents=True, exist_ok=True)

    def opt(key: str, default: str) -> str:
        return _conf_value(conf, f'global.{flavor.name}_{key}', default)

    parser = _new_ini_parser()
    if flavor.ini.exists():
        parser.read(flavor.ini, encoding='utf-8')

    for section in ('UI', 'Folders', 'EmuCore', 'EmuCore/GS', 'Achievements', 'InputSources', 'Hotkeys'):
        _ensure_section(parser, section)

    for key in ('MainWindowGeometry', 'MainWindowState'):
        if parser.has_option('UI', key):
            parser.remove_option('UI', key)

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

    parser.set('Folders', 'Bios',        str(bios_dir))
    parser.set('Folders', 'Snapshots',   str(SCREENSHOTS))
    parser.set('Folders', 'Savestates',  str(flavor.memcard_dir / 'sstates'))
    parser.set('Folders', 'MemoryCards', str(flavor.memcard_dir))
    parser.set('Folders', 'Logs',        str(USERDATA / 'system' / 'logs'))
    parser.set('Folders', 'Cache',       str(flavor.cache_dir))
    parser.set('Folders', 'Textures',    str(flavor.config_dir / 'textures'))

    parser.set('EmuCore', 'EnableDiscordPresence',       'false')
    fast_boot = opt('fastboot', '')
    parser.set('EmuCore', 'EnableFastBoot', 'false' if fast_boot == 'false' else 'true')
    parser.set('EmuCore', 'EnableCheats',                opt('cheats', 'false'))
    parser.set('EmuCore', 'EnableWideScreenPatches',     opt('EnableWideScreenPatches', 'false'))
    parser.set('EmuCore', 'EnableNoInterlacingPatches',  opt('interlacing_patches', 'false'))
    parser.set('EmuCore', 'SaveStateOnShutdown',         'true' if _conf_bool(conf, 'global.autosave') else 'false')

    parser.set('EmuCore/GS', 'Renderer',          opt('gfxbackend', '-1'))
    parser.set('EmuCore/GS', 'AspectRatio',        opt('ratio', 'Auto 4:3/3:2'))
    parser.set('EmuCore/GS', 'VsyncEnable',        opt('vsync', '0'))
    parser.set('EmuCore/GS', 'upscale_multiplier', opt('resolution', '1'))
    parser.set('EmuCore/GS', 'fxaa',               opt('fxaa', 'false'))
    parser.set('EmuCore/GS', 'FMVAspectRatioSwitch', opt('fmv_ratio', 'Auto 4:3/3:2'))
    parser.set('EmuCore/GS', 'mipmap_hw',          opt('mipmapping', '-1'))
    parser.set('EmuCore/GS', 'TriFilter',          opt('trilinear_filtering', '-1'))
    parser.set('EmuCore/GS', 'MaxAnisotropy',      opt('anisotropic_filtering', '0'))
    parser.set('EmuCore/GS', 'dithering_ps2',      opt('dithering', '2'))
    parser.set('EmuCore/GS', 'texture_preloading', opt('texture_loading', '2'))
    parser.set('EmuCore/GS', 'deinterlace_mode',   opt('deinterlacing', '0'))
    parser.set('EmuCore/GS', 'pcrtc_antiblur',     opt('blur', 'true'))
    parser.set('EmuCore/GS', 'IntegerScaling',     opt('scaling', 'false'))
    parser.set('EmuCore/GS', 'accurate_blending_unit', opt('blending', '1'))
    parser.set('EmuCore/GS', 'filter',             opt('texture_filtering', '2'))
    parser.set('EmuCore/GS', 'linear_present_mode', opt('bilinear_filtering', '1'))
    parser.set('EmuCore/GS', 'OsdShowMessages',    opt('osd_messages', 'true'))

    parser.set('Achievements', 'Enabled',           'false')
    parser.set('Achievements', 'TestMode',           'false')
    parser.set('Achievements', 'UnofficialTestMode', 'false')
    parser.set('Achievements', 'Notifications',      'true')
    parser.set('Achievements', 'SoundEffects',       'true')

    parser.set('InputSources', 'Keyboard', 'true')
    parser.set('InputSources', 'Mouse',    'true')
    parser.set('InputSources', 'SDL',      'true')

    parser.set('Hotkeys', 'ToggleFullscreen', 'Keyboard/Alt & Keyboard/Return')
    parser.set('Hotkeys', 'LoadStateFromSlot', 'Keyboard/F3')
    parser.set('Hotkeys', 'SaveStateToSlot',   'Keyboard/F1')
    parser.set('Hotkeys', 'NextSaveStateSlot', 'Keyboard/F2')
    parser.set('Hotkeys', 'OpenPauseMenu',     'Keyboard/Escape')
    parser.set('Hotkeys', 'TogglePause',       'Keyboard/Space')

    if bios_file is not None:
        _ensure_section(parser, 'Filenames')
        parser.set('Filenames', 'BIOS', bios_file)

    _ensure_section(parser, 'Pad')
    parser.set('Pad', 'MultitapPort1', 'false')
    parser.set('Pad', 'MultitapPort2', 'false')

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

    with flavor.ini.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote %s config: %s", flavor.name, flavor.ini)

PS2_BIOS_MIN_SIZE = 4 * 1024 * 1024
PS2_BIOS_MAX_SIZE = 8 * 1024 * 1024
ROMDIR_SEARCH_BYTES = 512 * 1024
ROMDIR_ENTRY_SIZE = 16

def _is_ps2_bios(path: Path) -> bool:
    if not PS2_BIOS_MIN_SIZE <= path.stat().st_size <= PS2_BIOS_MAX_SIZE:
        return False
    with path.open('rb') as fh:
        head = fh.read(ROMDIR_SEARCH_BYTES)
    return any(head[offset:offset + 6] == b'RESET\0' for offset in range(0, len(head), ROMDIR_ENTRY_SIZE))

def find_bios_dir(flavor: Pcsx2Flavor, bios_file: Optional[str]) -> Optional[Path]:
    for bios_dir in flavor.bios_dirs:
        if not bios_dir.is_dir():
            continue
        if bios_file is not None:
            if (bios_dir / bios_file).is_file():
                return bios_dir
        elif any(entry.is_file() and _is_ps2_bios(entry) for entry in bios_dir.iterdir()):
            return bios_dir
    return None

def _run_pcsx2(flavor: Pcsx2Flavor, ctx: LaunchContext, bios_file: Optional[str] = None) -> int:
    bin_path = _find_emulator_bin(flavor.name)
    if bin_path is None:
        _log.error("%s not found", flavor.name)
        return 1
    bios_dir = find_bios_dir(flavor, bios_file)
    if bios_dir is None:
        wanted = bios_file or 'PS2 BIOS'
        _log.error("%s: %s not found in %s", flavor.name, wanted, ', '.join(str(d) for d in flavor.bios_dirs))
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_pcsx2_config(flavor, bios_dir, conf, ctx, bios_file)
    controller_db = flavor.ini.parent / 'game_controller_db.txt'
    controller_db.write_text(generate_sdl_game_controller_config(ctx.controllers))

    cmd = [str(bin_path), '-nogui', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    if ctx.wheel:
        env.pop('SDL_GAMECONTROLLERCONFIG', None)
    result = _run_game_command(ctx, flavor.name, cmd, env, cwd=bin_path.parent)
    return result.returncode

def launch_pcsx2(ctx: LaunchContext) -> int:
    return _run_pcsx2(PCSX2, ctx)

def launch_armsx2(ctx: LaunchContext) -> int:
    return _run_pcsx2(ARMSX2, ctx)

NAMCO246_BIOS = 'r27v1602f.7d'
NAMCO256_BIOS = 'r27v1602f.8g'

def _read_acgame(rom: Path) -> configparser.ConfigParser:
    acgame = configparser.ConfigParser(interpolation=None, strict=False)
    acgame.optionxform = str
    acgame.read(rom, encoding='utf-8')
    return acgame

def launch_pcsx2x6(ctx: LaunchContext) -> int:
    if ctx.rom.suffix.lower() != '.acgame':
        _log.error("pcsx2x6 needs an .acgame file, got %s", ctx.rom.name)
        return 1
    acgame = _read_acgame(ctx.rom)
    gameid = acgame.get('game', 'gameid', fallback='')
    platform = acgame.get('game', 'platform', fallback='')
    data_dir = ctx.rom.parent / acgame.get('data', 'subdir', fallback=gameid)
    dongle = data_dir / acgame.get('data', 'dongle', fallback=f'{gameid}.ps2')
    if dongle.is_file():
        PCSX2X6.memcard_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(dongle, PCSX2X6.memcard_dir / dongle.name)
    bios_file = NAMCO246_BIOS if platform == '246' else NAMCO256_BIOS
    return _run_pcsx2(PCSX2X6, ctx, bios_file)
