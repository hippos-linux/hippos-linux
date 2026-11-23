from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path, PureWindowsPath

from HipposPaths import BIOS, CACHE, EMULATORS_ROOT, SAVES, USERDATA
from emulatorlauncher_registry import Emulator, register
from emulatorlauncher_shared import (
    WINE_NO_INSTALLER_PROMPTS,
    EmulatorNotInstalled,
    LaunchContext,
    _build_game_env,
    _ensure_section,
    _game_value,
    _load_hippos_conf,
    _new_ini_parser,
    _run_game_command,
    _sync_tree,
    generate_sdl_game_controller_config,
)

DEMUL_PACKAGE = EMULATORS_ROOT / 'demul' / 'demul'
DEMUL_PREFIX = USERDATA / 'wine-bottles' / 'demul'
DEMUL_DIR = DEMUL_PREFIX / 'demul'
WINE = Path('/opt/wine-builds/wine-proton/bin/wine')
DXVK = Path('/opt/dxvk')
DEFAULT_RESOLUTION = (1920, 1080)
GAELCO_RESOLUTION = (640, 480)
DLL_OVERRIDES = f'{WINE_NO_INSTALLER_PROMPTS};winegstreamer.exe=;winemenubuilder.exe=;' \
                'dxgi,d3d8,d3d9,d3d10core,d3d11,d3d12,d3d12core=n;nvapi64,nvapi='

DEMUL_SYSTEMS = {
    'naomi': 'naomi',
    'naomi2': 'naomi2',
    'atomiswave': 'awave',
    'dreamcast': 'dc',
    'hikaru': 'hikaru',
    'gaelco': 'gaelco',
    'cave3rd': 'cave3rd',
}
ROM_FOLDERS = ('naomi', 'naomi2', 'atomiswave', 'dreamcast', 'hikaru', 'gaelco', 'cave3rd')


def _windows_path(path: Path) -> str:
    return f'Z:{PureWindowsPath(path)}'


def install_program() -> None:
    if not (DEMUL_PACKAGE / 'demul.exe').is_file():
        raise EmulatorNotInstalled('demul')
    for source in DEMUL_PACKAGE.rglob('*'):
        if source.is_dir():
            continue
        target = DEMUL_DIR / source.relative_to(DEMUL_PACKAGE)
        if target.exists() and (target.suffix.lower() == '.ini' or target.stat().st_mtime >= source.stat().st_mtime):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def prepare_prefix() -> None:
    DEMUL_PREFIX.mkdir(parents=True, exist_ok=True)
    done = DEMUL_PREFIX / 'init.done'
    if not done.exists():
        env = dict(os.environ, WINEPREFIX=str(DEMUL_PREFIX), WINEDEBUG='-all', WINEDLLOVERRIDES=WINE_NO_INSTALLER_PROMPTS)
        subprocess.run([str(WINE), 'hostname'], env=env, check=False, capture_output=True)
        done.write_text('init')
    windows = DEMUL_PREFIX / 'drive_c' / 'windows'
    _sync_tree(DXVK / 'x64', windows / 'system32')
    _sync_tree(DXVK / 'x32', windows / 'syswow64')


def _write_ini(path: Path, settings: dict[str, dict[str, str]]) -> None:
    config = _new_ini_parser()
    if path.exists():
        with path.open(encoding='utf_8_sig') as fh:
            config.read_file(fh)
    for section, values in settings.items():
        _ensure_section(config, section)
        for key, value in values.items():
            config.set(section, key, value)
    with path.open('w', encoding='utf_8_sig') as fh:
        config.write(fh)


def write_demul_config(ctx: LaunchContext, system: str, nvram: Path) -> str:
    rom_paths = [BIOS, *(USERDATA / 'roms' / folder for folder in ROM_FOLDERS)]
    files = {'nvram': _windows_path(nvram), 'romsPathsCount': str(len(rom_paths))}
    files.update({f'roms{index}': _windows_path(path) for index, path in enumerate(rom_paths)})
    plugins = {
        'directory': _windows_path(DEMUL_DIR / 'plugins'),
        'spu': 'spuDemul.dll',
        'pad': 'padDemul.dll',
        'net': 'netDemul.dll',
        'gpu': 'gpuDX11old.dll' if system == 'gaelco' else 'gpuDX11.dll',
        'gdr': 'gdrCHD.dll' if system == 'dc' and ctx.rom.suffix.lower() == '.chd' else 'gdrImage.dll',
    }
    _write_ini(DEMUL_DIR / 'Demul.ini', {'files': files, 'plugins': plugins})
    return _windows_path(ctx.rom) if system == 'dc' else ctx.rom.stem


def write_gpu_config(ctx: LaunchContext, conf: dict[str, str], system: str) -> None:
    width, height = GAELCO_RESOLUTION if system == 'gaelco' else (ctx.resolution or DEFAULT_RESOLUTION)
    _write_ini(DEMUL_DIR / ('gpuDX11old.ini' if system == 'gaelco' else 'gpuDX11.ini'), {
        'main': {
            'UseFullscreen': '0',
            'aspect': _game_value(conf, ctx, 'demulRatio', '1'),
            'Vsync': _game_value(conf, ctx, 'demulVSync', '0'),
            'scaling': _game_value(conf, ctx, 'demulScaling', '1'),
        },
        'resolution': {'Width': str(width), 'Height': str(height)},
    })


def select_reshade_preset(system: str) -> None:
    preset = DEMUL_PACKAGE / f'ReShade.ini.{system}'
    shutil.copy2(preset if preset.is_file() else DEMUL_PACKAGE / 'ReShade.ini', DEMUL_DIR / 'ReShade.ini')


def launch_demul(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    system = DEMUL_SYSTEMS.get(ctx.system, ctx.system)
    nvram = SAVES / ctx.system
    nvram.mkdir(parents=True, exist_ok=True)
    install_program()
    prepare_prefix()
    game = write_demul_config(ctx, system, nvram)
    write_gpu_config(ctx, conf, system)
    select_reshade_preset(system)

    width, height = ctx.resolution or DEFAULT_RESOLUTION
    cmd = [str(WINE), 'explorer', f'/desktop=Wine,{width}x{height}',
           str(DEMUL_DIR / 'AutoHotkey32.exe'), 'newfullscreen.ahk', system, game]
    shader_cache = CACHE / 'demul'
    shader_cache.mkdir(parents=True, exist_ok=True)
    env = _build_game_env(conf, ctx)
    env.update({
        'WINEPREFIX': str(DEMUL_PREFIX),
        'WINEDEBUG': '-all',
        'WINEDLLOVERRIDES': DLL_OVERRIDES,
        'WINEESYNC': '0',
        'DXVK_ASYNC': '1',
        'DXVK_CONFIG_FILE': str(DXVK / 'dxvk.conf'),
        'DXVK_STATE_CACHE_PATH': str(shader_cache),
        'DXVK_LOG_LEVEL': 'none',
        'VKD3D_SHADER_CACHE_PATH': str(shader_cache),
        'SDL_GAMECONTROLLERCONFIG': generate_sdl_game_controller_config(ctx.controllers),
        'SDL_JOYSTICK_HIDAPI': '0',
    })
    return _run_game_command(ctx, cmd, env, cwd=DEMUL_DIR).returncode


register(Emulator('demul', launch_demul, packages=('demul',)))
