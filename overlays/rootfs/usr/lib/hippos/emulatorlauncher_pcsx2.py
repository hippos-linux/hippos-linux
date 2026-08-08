from __future__ import annotations

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


PCSX2_CONFIG_DIR   = CONFIGS / 'PCSX2'
PCSX2_INI          = PCSX2_CONFIG_DIR / 'inis' / 'PCSX2.ini'


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


def launch_pcsx2(ctx: LaunchContext) -> int:
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
