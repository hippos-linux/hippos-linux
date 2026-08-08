from __future__ import annotations

from typing import Optional

from emulatorlauncher_shared import (
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
)

from HipposPaths import CONFIGS, SAVES, SCREENSHOTS


AZAHAR_CONFIG_DIR  = CONFIGS / 'azahar-emu'
AZAHAR_INI         = AZAHAR_CONFIG_DIR / 'qt-config.ini'


_AZAHAR_BUTTONS: dict[str, str] = {
    'button_a':      'a',      'button_b':     'b',
    'button_x':      'x',      'button_y':     'y',
    'button_up':     'up',     'button_down':  'down',
    'button_left':   'left',   'button_right': 'right',
    'button_l':      'pageup', 'button_r':     'pagedown',
    'button_start':  'start',  'button_select':'select',
    'button_zl':     'l2',     'button_zr':    'r2',
    'button_home':   'hotkey',
}
_AZAHAR_HAT_DIR: dict[int, str] = {1: 'up', 2: 'right', 4: 'down', 8: 'left'}


def _write_azahar_config(conf: dict[str, str]) -> None:
    """Write Azahar qt-config.ini from hippos.conf values."""
    AZAHAR_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    parser = _new_ini_parser()
    if AZAHAR_INI.exists():
        parser.read(AZAHAR_INI, encoding='utf-8')

    for section in ('Layout', 'System', 'UI', 'Miscellaneous', 'Renderer', 'WebService', 'Utility'):
        _ensure_section(parser, section)

    # Layout
    screen_layout_raw = _conf_value(conf, 'global.azahar_screen_layout', '0-false')
    parts = screen_layout_raw.split('-', 1)
    layout_option = parts[0] if len(parts) > 0 else '0'
    swap_screen   = parts[1] if len(parts) > 1 else 'false'
    parser.set('Layout', 'custom_layout',    'false')
    parser.set('Layout', r'custom_layout\default', 'false')
    parser.set('Layout', 'swap_screen',      swap_screen)
    parser.set('Layout', r'swap_screen\default', 'false')
    parser.set('Layout', 'layout_option',    layout_option)
    parser.set('Layout', r'layout_option\default', 'false')
    parser.set('Layout', 'large_screen_proportion', _conf_value(conf, 'global.azahar_large_screen_proportion', '4'))
    parser.set('Layout', r'large_screen_proportion\default', 'false')

    # System
    is_new3ds = _conf_value(conf, 'global.azahar_is_new_3ds', '0')
    parser.set('System', 'is_new_3ds', 'true' if is_new3ds == '1' else 'false')
    parser.set('System', r'is_new_3ds\default', 'false')

    # UI
    parser.set('UI', 'fullscreen',    'true')
    parser.set('UI', r'fullscreen\default', 'false')
    parser.set('UI', 'displayTitleBars', 'false')
    parser.set('UI', r'displayTitleBars\default', 'false')
    parser.set('UI', 'firstStart',    'false')
    parser.set('UI', r'firstStart\default', 'false')
    parser.set('UI', 'hideInactiveMouse', 'true')
    parser.set('UI', r'hideInactiveMouse\default', 'false')
    parser.set('UI', 'enable_discord_presence', 'false')
    parser.set('UI', r'enable_discord_presence\default', 'false')
    parser.set('UI', 'calloutFlags', '1')
    parser.set('UI', r'calloutFlags\default', 'false')
    parser.set('UI', 'confirmClose', 'false')
    parser.set('UI', r'confirmClose\default', 'false')
    parser.set('UI', r'Paths\screenshotPath', str(SCREENSHOTS))
    parser.set('UI', r'Paths\screenshotPath\default', 'false')

    # Miscellaneous
    parser.set('Miscellaneous', 'check_for_update_on_start', 'false')
    parser.set('Miscellaneous', r'check_for_update_on_start\default', 'false')

    # Renderer
    graphics_api = _conf_value(conf, 'global.azahar_graphics_api', '1')
    parser.set('Renderer', 'graphics_api', graphics_api)
    parser.set('Renderer', r'graphics_api\default', 'true')
    use_hw = _conf_value(conf, 'global.azahar_use_hw_shader', '0')
    parser.set('Renderer', 'use_hw_shader', 'true' if use_hw == '1' else 'false')
    parser.set('Renderer', r'use_hw_shader\default', 'false')
    acc_mul = _conf_value(conf, 'global.azahar_accurate_multiplication', '0')
    parser.set('Renderer', 'shaders_accurate_mul', 'true' if acc_mul == '1' else 'false')
    parser.set('Renderer', r'shaders_accurate_mul\default', 'false')
    jit = _conf_value(conf, 'global.azahar_use_shader_jit', '1')
    parser.set('Renderer', 'use_shader_jit', 'true' if jit != '0' else 'false')
    parser.set('Renderer', r'use_hw_shader_jit\default', 'false')
    async_shaders = _conf_value(conf, 'global.azahar_async_shader_compilation', '0')
    parser.set('Renderer', 'async_shader_compilation', 'true' if async_shaders == '1' else 'false')
    parser.set('Renderer', r'async_shader_compilation\default', 'false')
    async_pres = _conf_value(conf, 'global.azahar_async_presentation', '0')
    parser.set('Renderer', 'async_presentation', 'true' if async_pres == '1' else 'false')
    parser.set('Renderer', r'async_presentation\default', 'false')
    vsync = _conf_value(conf, 'global.azahar_use_vsync_new', '1')
    parser.set('Renderer', 'use_vsync_new', 'true' if vsync != '0' else 'false')
    parser.set('Renderer', r'use_vsync_new\default', 'false')
    res_factor = _conf_value(conf, 'global.azahar_resolution_factor', '1')
    parser.set('Renderer', 'resolution_factor', res_factor)
    parser.set('Renderer', r'resolution_factor\default', 'false')

    # Utility
    disk_cache = _conf_value(conf, 'global.azahar_use_disk_shader_cache', '0')
    parser.set('Utility', 'use_disk_shader_cache', 'true' if disk_cache == '1' else 'false')
    parser.set('Utility', r'use_disk_shader_cache\default', 'false')

    # WebService
    parser.set('WebService', 'enable_telemetry', 'false')
    parser.set('WebService', r'enable_telemetry\default', 'false')

    with AZAHAR_INI.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote Azahar config: %s", AZAHAR_INI)


def _azahar_button_str(es_name: str, guid: str, inputs: dict) -> Optional[str]:
    binding = inputs.get(es_name)
    if binding is None:
        return None
    if binding.type == 'button':
        return f'button:{binding.code},guid:{guid},engine:sdl'
    if binding.type == 'hat':
        direction = _AZAHAR_HAT_DIR.get(abs(binding.value), 'up')
        return f'engine:sdl,guid:{guid},hat:{binding.code},direction:{direction}'
    if binding.type == 'axis':
        return f'engine:sdl,guid:{guid},axis:{binding.code},direction:+,threshold:0.5'
    return None


def _write_azahar_controller_config(ctx: LaunchContext) -> None:
    """Write Azahar Controls INI section from ES controller profile."""
    profiles = _load_es_input_configs()
    p1 = next((c for c in ctx.controllers if c.player == 1), None)
    if p1 is None:
        return
    profile = _pick_es_profile(profiles, p1)
    if profile is None:
        return

    cfg_path = AZAHAR_INI
    parser = _new_ini_parser()
    if cfg_path.exists():
        parser.read(cfg_path, encoding='utf-8')

    _ensure_section(parser, 'Controls')

    # Profile boilerplate
    if not parser.has_option('Controls', r'profiles\size'):
        parser.set('Controls', 'profile',                    '0')
        parser.set('Controls', r'profile\default',           'false')
        parser.set('Controls', r'profiles\1\name',           'default')
        parser.set('Controls', r'profiles\1\name\default',   'false')
        parser.set('Controls', r'profiles\size',             '1')
        parser.set('Controls', r'profiles\size\default',     'false')

    guid = p1.guid
    for ini_key, es_name in _AZAHAR_BUTTONS.items():
        val = _azahar_button_str(es_name, guid, profile.inputs)
        if val is not None:
            parser.set('Controls', rf'profiles\1\{ini_key}',           f'"{val}"')
            parser.set('Controls', rf'profiles\1\{ini_key}\default',   'false')

    # Analog sticks
    for ini_key, js_prefix in (('circle_pad', 'joystick1'), ('c_stick', 'joystick2')):
        bx = profile.inputs.get(f'{js_prefix}left')
        by = profile.inputs.get(f'{js_prefix}up')
        if bx and by and bx.type == 'axis' and by.type == 'axis':
            val = f'axis_x:{bx.code},guid:{guid},axis_y:{by.code},engine:sdl'
            parser.set('Controls', rf'profiles\1\{ini_key}',           f'"{val}"')
            parser.set('Controls', rf'profiles\1\{ini_key}\default',   'false')

    with cfg_path.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote Azahar controller config: %s", cfg_path)


def launch_azahar(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('azahar')
    if bin_path is None:
        _log.error("azahar not found")
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_azahar_config(conf)
    _write_azahar_controller_config(ctx)
    cmd = [str(bin_path), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_DATA_HOME']   = str(SAVES / '3ds')
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    result = _run_game_command(ctx, 'azahar', cmd, env)
    return result.returncode
