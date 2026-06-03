from __future__ import annotations

from pathlib import Path
from typing import Optional

from emulatorlauncher_impl import (
    CACHE,
    LaunchContext,
    SHADPS4_BUNDLE_DIR,
    SHADPS4_CONFIG_DIR,
    SHADPS4_ROM_DIR,
    SHADPS4_RUNTIME_DIR,
    SHADPS4_SAVES,
    SHADPS4_TOML,
    SHADPS4_USER_CONFIG_DIR,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _display_resolution_from_conf,
    _find_emulator_bin,
    _find_executable,
    _load_effective_hippos_conf,
    _read_toml,
    _run_game_command,
    _sync_tree,
    _write_toml,
)


def _shadps4_base_config(display_resolution: Optional[tuple[int, int]]) -> dict[str, object]:
    width, height = display_resolution if display_resolution is not None else (1280, 720)
    return {
        'General': {
            'isPS4Pro': False,
            'isTrophyPopupDisabled': False,
            'trophyNotificationDuration': 6.0,
            'playBGM': False,
            'BGMvolume': 50,
            'enableDiscordRPC': False,
            'logFilter': '',
            'logType': 'async',
            'userName': 'HippOS',
            'updateChannel': 'Release',
            'chooseHomeTab': 'General',
            'showSplash': False,
            'autoUpdate': False,
            'alwaysShowChangelog': False,
            'sideTrophy': 'right',
            'separateUpdateEnabled': False,
            'compatibilityEnabled': False,
            'checkCompatibilityOnStartup': False,
        },
        'Input': {
            'cursorState': 1,
            'cursorHideTimeout': 5,
            'backButtonBehavior': 'left',
            'useSpecialPad': False,
            'specialPadClass': 1,
            'isMotionControlsEnabled': True,
            'useUnifiedInputConfig': True,
        },
        'GPU': {
            'screenWidth': int(width),
            'screenHeight': int(height),
            'nullGpu': False,
            'copyGPUBuffers': False,
            'dumpShaders': False,
            'patchShaders': True,
            'vblankDivider': 1,
            'Fullscreen': True,
            'FullscreenMode': 'Fullscreen (Borderless)',
            'allowHDR': False,
        },
        'Vulkan': {
            'gpuId': -1,
            'validation': False,
            'validation_sync': False,
            'validation_gpu': False,
            'crashDiagnostic': False,
            'hostMarkers': False,
            'guestMarkers': False,
            'rdocEnable': False,
        },
        'Debug': {
            'DebugDump': False,
            'CollectShader': False,
            'isSeparateLogFilesEnabled': False,
            'FPSColor': True,
        },
        'Keys': {
            'TrophyKey': '',
        },
        'GUI': {
            'installDirs': [str(SHADPS4_ROM_DIR)],
            'saveDataPath': str(SHADPS4_SAVES),
            'loadGameSizeEnabled': True,
            'addonInstallDir': str(SHADPS4_ROM_DIR / 'DLC'),
            'emulatorLanguage': 'en_US',
            'backgroundImageOpacity': 50,
            'showBackgroundImage': True,
            'mw_width': int(width),
            'mw_height': int(height),
            'theme': 0,
            'iconSize': 36,
            'sliderPos': 0,
            'iconSizeGrid': 69,
            'sliderPosGrid': 0,
            'gameTableMode': 0,
            'geometry_x': 0,
            'geometry_y': 0,
            'geometry_w': int(width),
            'geometry_h': int(height),
            'pkgDirs': [str(SHADPS4_ROM_DIR)],
            'elfDirs': [],
            'recentFiles': [],
        },
        'Settings': {
            'consoleLanguage': 1,
        },
    }


def write_shadps4_config(ctx: LaunchContext) -> None:
    conf = _load_effective_hippos_conf()
    display_resolution = _display_resolution_from_conf(conf)
    config = _read_toml(SHADPS4_TOML) or _shadps4_base_config(display_resolution)
    if not config:
        config = _shadps4_base_config(display_resolution)

    SHADPS4_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if SHADPS4_BUNDLE_DIR.exists():
        _sync_tree(SHADPS4_BUNDLE_DIR, SHADPS4_RUNTIME_DIR)

    for section, defaults in _shadps4_base_config(display_resolution).items():
        section_config = config.setdefault(section, {})
        if isinstance(section_config, dict):
            for key, value in defaults.items():
                section_config.setdefault(key, value)

    general = config.setdefault('General', {})
    general['autoUpdate'] = False
    general['enableDiscordRPC'] = False
    general['userName'] = 'HippOS'

    gpu = config.setdefault('GPU', {})
    gpu['Fullscreen'] = True
    gpu['FullscreenMode'] = 'Fullscreen (Borderless)'
    if display_resolution is not None:
        gpu['screenWidth'] = int(display_resolution[0])
        gpu['screenHeight'] = int(display_resolution[1])

    gui = config.setdefault('GUI', {})
    gui['addonInstallDir'] = str(SHADPS4_ROM_DIR / 'DLC')
    gui['installDirs'] = [str(SHADPS4_ROM_DIR)]
    gui['saveDataPath'] = str(SHADPS4_SAVES)
    if display_resolution is not None:
        gui['mw_width'] = int(display_resolution[0])
        gui['mw_height'] = int(display_resolution[1])
        gui['geometry_w'] = int(display_resolution[0])
        gui['geometry_h'] = int(display_resolution[1])
    gui['pkgDirs'] = [str(SHADPS4_ROM_DIR)]

    vulkan_cfg = config.setdefault('Vulkan', {})
    vulkan_cfg['gpuId'] = int(vulkan_cfg.get('gpuId', -1))

    gpu['allowHDR'] = _conf_bool(conf, 'shadps4_hdr', False)
    settings = config.setdefault('Settings', {})
    lang_value = _conf_value(conf, 'shadps4_console_lang', '')
    settings['consoleLanguage'] = int(lang_value) if lang_value else 1

    SHADPS4_USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SHADPS4_SAVES.mkdir(parents=True, exist_ok=True)
    SHADPS4_ROM_DIR.mkdir(parents=True, exist_ok=True)
    _write_toml(SHADPS4_TOML, config)


def launch_shadps4(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('shadps4')
    if bin_path is None:
        return 1

    write_shadps4_config(ctx)
    runtime_exe = _find_executable(SHADPS4_RUNTIME_DIR) or bin_path
    if not runtime_exe.exists():
        return 1

    if ctx.rom.name == 'config':
        launch_target = None
    elif ctx.rom.suffix.lower() == '.ps4' and (ctx.rom.parent / 'eboot.bin').exists():
        launch_target = ctx.rom.parent / 'eboot.bin'
    elif ctx.rom.is_dir() and (ctx.rom / 'eboot.bin').exists():
        launch_target = ctx.rom / 'eboot.bin'
    else:
        launch_target = ctx.rom

    conf = _load_effective_hippos_conf()
    cmd = [str(runtime_exe)]
    if launch_target is not None:
        cmd.append(str(launch_target))

    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    env['HOME'] = str(Path('/userdata/system'))
    env['XDG_CONFIG_HOME'] = str(SHADPS4_CONFIG_DIR)
    env['XDG_DATA_HOME'] = str(SHADPS4_RUNTIME_DIR)
    env['XDG_CACHE_HOME'] = str(CACHE / 'shadps4')
    result = _run_game_command(ctx, 'shadps4', cmd, env, cwd=SHADPS4_RUNTIME_DIR)
    return result.returncode
