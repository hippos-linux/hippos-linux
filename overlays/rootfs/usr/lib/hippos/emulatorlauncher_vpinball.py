from __future__ import annotations
from pathlib import Path

from shutil import copyfile

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _display_resolution_from_conf,
    _find_emulator_bin,
    _load_effective_hippos_conf,
    _new_ini_parser,
    _run_game_command,
    generate_sdl_game_controller_config,
)

from HipposPaths import CONFIGS


def write_vpinball_config(ctx: LaunchContext) -> None:
    conf = _load_effective_hippos_conf()
    VPINBALL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    VPINBALL_PINMAME_INI.mkdir(parents=True, exist_ok=True)

    if not VPINBALL_INI.exists():
        if VPINBALL_DEFAULT_INI.exists():
            copyfile(VPINBALL_DEFAULT_INI, VPINBALL_INI)
        else:
            VPINBALL_INI.write_text('', encoding='utf-8')
    if VPINBALL_LOG.exists():
        VPINBALL_LOG.rename(VPINBALL_LOG.with_suffix(f'{VPINBALL_LOG.suffix}.1'))

    parser = _new_ini_parser()
    parser.read(VPINBALL_INI, encoding='utf-8')
    for section in ('Standalone', 'Player', 'TableOverride'):
        if not parser.has_section(section):
            parser.add_section(section)

    parser.set('Standalone', 'PinMAMEPath', './' if _conf_bool(conf, 'vpinball_folders', True) else '')
    balltrail = _conf_value(conf, 'vpinball_balltrail', '0')
    parser.set('Player', 'BallTrail', '0' if balltrail == '0' else '1')
    parser.set('Player', 'BallTrailStrength', balltrail)
    parser.set('Player', 'NudgeStrength', _conf_value(conf, 'vpinball_nudgestrength', ''))
    parser.set('Player', 'MaxFramerate', _conf_value(conf, 'vpinball_maxframerate', ''))
    parser.set('Player', 'SyncMode', _conf_value(conf, 'vpinball_vsync', '2'))
    parser.set('Player', 'ExitGameKey', '62')

    presets = _conf_value(conf, 'vpinball_presets', 'manual')
    if presets != 'manual':
        match presets:
            case 'highend':
                fxaa, sharpen, disable_ao, dynamic_ao, ssrefl, pfreflection, force_filtering, alpha_accuracy = ('3', '2', '0', '1', '1', '5', '1', '10')
            case 'lowend':
                fxaa, sharpen, disable_ao, dynamic_ao, ssrefl, pfreflection, force_filtering, alpha_accuracy = ('0', '0', '1', '0', '0', '3', '0', '5')
            case _:
                fxaa = sharpen = disable_ao = dynamic_ao = ssrefl = pfreflection = force_filtering = alpha_accuracy = ''
        parser.set('Player', 'FXAA', fxaa)
        parser.set('Player', 'Sharpen', sharpen)
        parser.set('Player', 'DisableAO', disable_ao)
        parser.set('Player', 'DynamicAO', dynamic_ao)
        parser.set('Player', 'SSRefl', ssrefl)
        parser.set('Player', 'PFReflection', pfreflection)
        parser.set('Player', 'ForceAnisotropicFiltering', force_filtering)
        parser.set('Player', 'AlphaRampAccuracy', alpha_accuracy)

    if _conf_bool(conf, 'vpinball_customphysicalsetup', False):
        screen_width = _conf_value(conf, 'vpinball_screenwidth', '')
        screen_height = _conf_value(conf, 'vpinball_screenheight', '')
        inclination = _conf_value(conf, 'vpinball_screeninclination', '')
        screen_y = _conf_value(conf, 'vpinball_screenplayery', '')
        screen_z = _conf_value(conf, 'vpinball_screenplayerz', '')
    else:
        screen_width = screen_height = inclination = screen_y = screen_z = ''

    parser.set('Player', 'ScreenWidth', screen_width)
    parser.set('Player', 'ScreenHeight', screen_height)
    parser.set('Player', 'ScreenInclination', inclination)
    parser.set('Player', 'ScreenPlayerY', screen_y)
    parser.set('Player', 'ScreenPlayerZ', screen_z)
    parser.set('Standalone', 'AltColor', '1' if _conf_bool(conf, 'vpinball_altcolor', True) else '0')
    parser.set('Player', 'MusicVolume', _conf_value(conf, 'vpinball_musicvolume', ''))
    parser.set('Player', 'SoundVolume', _conf_value(conf, 'vpinball_soundvolume', ''))
    parser.set('Standalone', 'AltSound', '1' if _conf_bool(conf, 'vpinball_altsound', True) else '0')
    parser.set('Player', 'SoundDevice', _conf_value(conf, 'vpinball_sounddevice', ''))
    parser.set('Player', 'SoundDeviceBG', _conf_value(conf, 'vpinball_sounddevicebg', ''))
    parser.set('Player', 'JoyAddCreditKey', '1' if _conf_bool(conf, 'vpinball_pad_add_credit', False) else '0')
    parser.set('Player', 'PBWEnabled', '1' if _conf_bool(conf, 'vpinball_pbw', True) else '0')

    display_resolution = _display_resolution_from_conf(conf)
    screen_width, screen_height = display_resolution if display_resolution is not None else (1280, 720)
    if display_resolution is not None:
        parser.set('Player', 'WindowPosX', '0')
        parser.set('Player', 'WindowPosY', '0')
        parser.set('Player', 'Width', str(screen_width))
        parser.set('Player', 'Height', str(screen_height))
    parser.set('Player', 'FullScreen', '0')
    parser.set('TableOverride', 'ViewCabMode', '2')
    parser.set('TableOverride', 'ViewCabRotation', '0')
    parser.set('Standalone', 'DMDServer', '0')

    playfield_mode = _conf_value(conf, 'vpinball_playfieldmode', '')
    if playfield_mode:
        parser.set('Player', 'BGSet', playfield_mode)
    else:
        parser.set('Player', 'BGSet', '1' if screen_width < screen_height else '0')

    def _vpinball_set_window(window_name: str, choice: str, *, default_ratio: float, default_width_pct: int = 25) -> None:
        if choice == 'manual':
            return
        if choice == 'disabled':
            parser.set('Standalone', window_name, '0')
            return

        parser.set('Standalone', window_name, '1')
        width_pct = default_width_pct
        if choice.endswith('_small'):
            width_pct = 20
        elif choice.endswith('_medium'):
            width_pct = 25
        elif choice.endswith('_large'):
            width_pct = 30
        x_pct = 100 - width_pct if choice.startswith('topright') else 0
        y_pct = 0
        if choice == 'screen2' or choice == 'screen3':
            x_pct = 0
            y_pct = 0
        width = int(screen_width * width_pct / 100)
        height = int(width / default_ratio) if default_ratio else width
        parser.set('Standalone', f'{window_name}X', str(int(screen_width * x_pct / 100)))
        parser.set('Standalone', f'{window_name}Y', str(int(screen_height * y_pct / 100)))
        parser.set('Standalone', f'{window_name}Width', str(width))
        parser.set('Standalone', f'{window_name}Height', str(height))

    _vpinball_set_window('PinMAMEWindow', _conf_value(conf, 'vpinball_pinmame', 'manual'), default_ratio=4.0)
    _vpinball_set_window('FlexDMDWindow', _conf_value(conf, 'vpinball_flexdmd', 'manual'), default_ratio=4.0)
    _vpinball_set_window('B2SBackglass', _conf_value(conf, 'vpinball_b2s', 'manual'), default_ratio=4 / 3)
    if _conf_value(conf, 'vpinball_b2s', 'manual') == 'disabled':
        parser.set('Standalone', 'B2SWindows', '0')
    else:
        parser.set('Standalone', 'B2SWindows', '1')

    b2sdmd_choice = _conf_value(conf, 'vpinball_b2sdmd', 'true').lower()
    parser.set('Standalone', 'B2SHideB2SDMD', '0' if b2sdmd_choice in ('1', 'true', 'yes', 'on') else '1')
    b2sgrill_choice = _conf_value(conf, 'vpinball_b2sgrill', 'true').lower()
    parser.set('Standalone', 'B2SHideGrill', '0' if b2sgrill_choice in ('1', 'true', 'yes', 'on') else '1')

    dmd_size = _conf_value(conf, 'vpinball_dmdsize', '128x32')
    if dmd_size == '128x16':
        parser.set('Standalone', 'B2SDMDX', '0')
        parser.set('Standalone', 'B2SDMDY', '0')
        parser.set('Standalone', 'B2SDMDWidth', '1024')
        parser.set('Standalone', 'B2SDMDHeight', '128')
    elif dmd_size == '192x64':
        parser.set('Standalone', 'B2SDMDX', '0')
        parser.set('Standalone', 'B2SDMDY', '0')
        parser.set('Standalone', 'B2SDMDWidth', '1024')
        parser.set('Standalone', 'B2SDMDHeight', '341')
    elif dmd_size == '256x64':
        parser.set('Standalone', 'B2SDMDX', '0')
        parser.set('Standalone', 'B2SDMDY', '0')
        parser.set('Standalone', 'B2SDMDWidth', '1024')
        parser.set('Standalone', 'B2SDMDHeight', '128')
    else:
        parser.set('Standalone', 'B2SDMDX', '0')
        parser.set('Standalone', 'B2SDMDY', '0')
        parser.set('Standalone', 'B2SDMDWidth', '1024')
        parser.set('Standalone', 'B2SDMDHeight', '256')

    with VPINBALL_INI.open('w', encoding='utf-8') as fh:
        parser.write(fh)


def launch_vpinball(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('vpinball')
    if bin_path is None:
        return 1

    write_vpinball_config(ctx)
    conf = _load_hippos_conf()
    cmd = [str(bin_path), '-PrefPath', str(VPINBALL_CONFIG_DIR), '-Ini', str(VPINBALL_INI), '-Play', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    env['SDL_RENDER_VSYNC'] = '0'
    result = _run_game_command(ctx, 'vpinball', cmd, env)
    return result.returncode


VPINBALL_CONFIG_DIR = CONFIGS / 'vpinball'
VPINBALL_INI = VPINBALL_CONFIG_DIR / 'VPinballX.ini'
VPINBALL_LOG = VPINBALL_CONFIG_DIR / 'vpinball.log'
VPINBALL_PINMAME_INI = VPINBALL_CONFIG_DIR / 'pinmame' / 'ini'
VPINBALL_DEFAULT_INI = Path('/usr/bin/vpinball/assets/Default_VPinballX.ini')
