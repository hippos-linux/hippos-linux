from __future__ import annotations

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_bool,
    _conf_int,
    _find_emulator_bin,
    _load_hippos_conf,
    _log,
    _read_toml,
    _run_game_command,
    _write_toml,
)

from HipposPaths import BIOS, CONFIGS, SAVES


MELONDS_CONFIG_DIR = CONFIGS / 'melonDS'
MELONDS_TOML       = MELONDS_CONFIG_DIR / 'melonDS.toml'


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


def launch_melonds(ctx: LaunchContext) -> int:
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
