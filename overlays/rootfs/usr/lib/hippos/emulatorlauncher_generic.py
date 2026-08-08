from __future__ import annotations
import os
import configparser
from pathlib import Path
from typing import Optional

from emulatorlauncher_shared import (
    ControllerInfo,
    LaunchContext,
    _build_game_env,
    _conf_bool,
    _conf_int,
    _conf_value,
    _find_emulator_bin,
    _load_es_input_configs,
    _load_hippos_conf,
    _log,
    _pick_es_profile,
    _ra_analog_dpad_mode,
    _ra_binding_value,
    _ra_btn_map_for_ctx,
    _ra_type_suffix,
    _run_game_command,
)

from HipposPaths import BIOS, CHEATS, CONFIGS, SAVES, SCREENSHOTS, USERDATA, USER_DECORATIONS, USER_SHADERS


def launch_libretro(ctx: LaunchContext) -> int:
    if not ctx.core:
        _log.error("No core configured for system '%s'", ctx.system)
        return 1

    core_path = find_core(ctx.core)
    if core_path is None:
        _log.error(
            "Core '%s_libretro.so' not found. Searched:\n  %s",
            ctx.core,
            '\n  '.join(str(p) for p in _core_search_paths()),
        )
        return 1

    conf = _load_hippos_conf()
    _write_retroarch_core_options(ctx, conf)
    ra_cfg = _write_retroarch_config(ctx.controllers, ctx)
    ra_game_cfg = _write_retroarch_game_overrides(ctx)
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    cmd = [
        str(RETROARCH_BIN),
        '--verbose',
        '--log-file', str(USERDATA / 'system' / 'logs' / 'retroarch.log'),
        '-L', str(core_path),
        '--config', str(ra_cfg),
    ]
    if ra_game_cfg is not None:
        cmd += ['--appendconfig', str(ra_game_cfg)]
    cmd.append(str(ctx.rom))
    _log.info("Launching: %s", ' '.join(cmd))

    env = _build_game_env(conf, ctx)
    try:
        result = _run_game_command(ctx, 'retroarch', cmd, env)
    finally:
        if ra_game_cfg is not None:
            ra_game_cfg.unlink(missing_ok=True)
    return result.returncode


# Emulators that accept a CLI fullscreen flag before the ROM argument.
# Quake-engine ports use Quake console syntax (+set), others use standard flags.
_FULLSCREEN_FLAGS: dict[str, list[str]] = {
    # Quake-engine ports
    'vkquake':        ['-fullscreen'],
    'vkquake2':       ['-fullscreen'],
    'vkquake3':       ['-fullscreen'],
    'yquake2':        ['-fullscreen'],
    'iortcw':         ['+set', 'r_fullscreen', '1'],
    'openjk':         ['+set', 'r_fullscreen', '1'],
    'openjkdf2':      ['+set', 'r_fullscreen', '1'],
    'openmohaa':      ['+set', 'r_fullscreen', '1'],
    'dhewm3':         ['+set', 'r_fullscreen', '1'],
    'etlegacy':       ['+set', 'r_fullscreen', '1'],
    # Other ports still on _launch_standalone
    'devilutionx':    ['--fullscreen'],
    'raze':           ['-fullscreen'],
    'ecwolf':         ['--fullscreen'],
    'xash3d_fwgs':    ['-fullscreen'],
    'dxx-rebirth':    ['--fullscreen'],
    'hurrican':       ['--fullscreen'],
    'openjazz':       ['-f'],
    'jazz2-native':   ['--fullscreen'],
    'cdogs':          ['--fullscreen'],
    'cgenius':        ['--fullscreen'],
    'sdlpop':         ['--fullscreen'],
    'mugen':          ['-f'],
}


def launch_standalone(ctx: LaunchContext) -> int:
    """Generic launcher for standalone emulators under /opt/emulators or user path."""
    bin_path = _find_emulator_bin(ctx.emulator)
    if bin_path is None:
        _log.error(
            "Emulator '%s' not installed. Expected binary at "
            "/opt/emulators/%s/%s, /userdata/emulators/%s/current/%s, "
            "or system PATH",
            ctx.emulator, ctx.emulator, ctx.emulator,
            ctx.emulator, ctx.emulator,
        )
        return 1

    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    conf = _load_hippos_conf()
    fullscreen_flags = _FULLSCREEN_FLAGS.get(ctx.emulator, [])
    cmd = [str(bin_path)] + fullscreen_flags + [str(ctx.rom)]
    _log.info("Launching standalone: %s", ' '.join(cmd))

    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, ctx.emulator, cmd, env)
    return result.returncode


RA_CONFIG_DIR = CONFIGS / 'retroarch'
RA_CUSTOM_CFG = RA_CONFIG_DIR / 'retroarchcustom.cfg'
RA_CORES_CFG  = RA_CONFIG_DIR / 'cores' / 'retroarch-core-options.cfg'

RETROARCH_BIN = Path('/usr/bin/retroarch')


LIBRETRO_RATIO_INDEXES: tuple[str, ...] = (
    '4/3', '16/9', '16/10', '16/15', '21/9', '1/1', '2/1', '3/2', '3/4',
    '4/1', '9/16', '5/4', '6/5', '7/9', '8/3', '8/7', '19/12', '19/14',
    '30/17', '32/9', 'config', 'squarepixel', 'core', 'custom', 'full',
)


CORE_SEARCH_PATHS = [
    USERDATA / 'emulators' / 'retroarch' / 'current' / 'cores',
    Path('/opt/emulators/retroarch/cores'),
    USERDATA / 'emulators' / 'retroarch' / 'cores',
    Path('/usr/lib/x86_64-linux-gnu/libretro'),
    Path('/usr/lib/aarch64-linux-gnu/libretro'),
    Path('/usr/lib/libretro'),
]

LIBRETRO_CORE_ALIASES: dict[str, tuple[str, ...]] = {
    'beetle-saturn': ('mednafen_saturn',),
    'bsnes_hd': ('bsnes_hd_beta',),
    'genesis_plus_gx-wide': ('genesis_plus_gx_wide',),
    'mame078plus': ('mame2003_plus',),
    'pce': ('mednafen_pce',),
    'pce_fast': ('mednafen_pce_fast',),
    'pcfx': ('mednafen_pcfx',),
    'vb': ('mednafen_vb',),
    'vba-m': ('vbam',),
}


def _ratio_index(conf: dict[str, str]) -> int:
    ratio = _conf_value(conf, 'global.ratio', 'core')
    if ratio in LIBRETRO_RATIO_INDEXES:
        return LIBRETRO_RATIO_INDEXES.index(ratio)
    return LIBRETRO_RATIO_INDEXES.index('core')


def _core_search_paths() -> list[Path]:
    paths = list(CORE_SEARCH_PATHS[:2])
    paths.extend(
        path
        for path in sorted(Path('/opt/emulators').glob('*/cores'))
        if path not in paths
    )
    paths.extend(CORE_SEARCH_PATHS[2:])
    return paths


def find_core(core_name: str) -> Optional[Path]:
    for candidate_core in (core_name, *LIBRETRO_CORE_ALIASES.get(core_name, ())):
        filename = f'{candidate_core}_libretro.so'
        for search_dir in _core_search_paths():
            candidate = search_dir / filename
            if candidate.exists():
                if candidate_core != core_name:
                    _log.info("Resolved libretro core alias %s -> %s", core_name, candidate_core)
                return candidate
    return None


_CORE_P1_DEVICE: dict[str, str] = {
    'atari800': '513', 'cap32': '513', '81': '259', 'fuse': '769',
    'mupen64plus_next': '1', 'parallel_n64': '1',
    'beetle_pce': '769', 'beetle_pce_fast': '769',  # PCE 6-button
    'genesisplusgx': '513', 'picodrive': '513',      # MD 6-button
    'genesis_plus_gx': '513',
    'prosystem': '1',   # 7800 pad
}
_CORE_P2_DEVICE: dict[str, str] = {
    'atari800': '513', 'fuse': '513',
    'genesisplusgx': '513', 'picodrive': '513',
    'genesis_plus_gx': '513',
}


_SYSTEM_P1_DEVICE: dict[str, str] = {
    'msx': '1', 'msx1': '1', 'msx2': '1', 'msx2+': '1', 'msxturbor': '1',
    'colecovision': '1',
}
_SYSTEM_P2_DEVICE: dict[str, str] = {
    'msx': '1', 'msx1': '1', 'msx2': '1', 'msx2+': '1', 'msxturbor': '1',
    'colecovision': '1',
}


_COMPLEX_DEVICE_SYSTEMS: frozenset[str] = frozenset({
    'snes', 'nes', 'psx', 'megadrive', 'mastersystem', 'saturn', 'pce',
    'pcenginecd', 'supergrafx', 'wii', 'gamecube',
})


def _set_libretro_device_types(
    cfg: _KVConfig,
    ctx: LaunchContext,
    conf: dict[str, str],
) -> None:
    """Write input_libretro_device_pN keys to retroarch cfg."""
    core    = ctx.core
    system  = ctx.system
    nplayers = max((c.player for c in ctx.controllers), default=2)

    # Default: RETRO_DEVICE_JOYPAD = 1 for all ports
    for i in range(1, nplayers + 1):
        cfg.set(f'input_libretro_device_p{i}', '"1"')

    if system in _COMPLEX_DEVICE_SYSTEMS:
        _set_complex_device_types(cfg, ctx, conf, nplayers)
        return

    # Core-level override
    if core in _CORE_P1_DEVICE:
        cfg.set('input_libretro_device_p1', f'"{_CORE_P1_DEVICE[core]}"')
    elif system in _SYSTEM_P1_DEVICE:
        cfg.set('input_libretro_device_p1', f'"{_SYSTEM_P1_DEVICE[system]}"')

    if core in _CORE_P2_DEVICE:
        cfg.set('input_libretro_device_p2', f'"{_CORE_P2_DEVICE[core]}"')
    elif system in _SYSTEM_P2_DEVICE:
        cfg.set('input_libretro_device_p2', f'"{_SYSTEM_P2_DEVICE[system]}"')


def _set_complex_device_types(
    cfg: _KVConfig,
    ctx: LaunchContext,
    conf: dict[str, str],
    nplayers: int,
) -> None:
    system = ctx.system
    core   = ctx.core

    if system == 'snes':
        p1 = conf.get(f'controller1_{core}') or conf.get('controller1_snes9x', '1')
        p2 = conf.get(f'controller2_{core}') or conf.get('controller2_snes9x', '257')
        cfg.set('input_libretro_device_p1', f'"{p1}"')
        cfg.set('input_libretro_device_p2', f'"{p2}"')
        cfg.set('input_libretro_device_p3', f'"{conf.get("controller3_snes9x", "1")}"')

    elif system == 'nes':
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_nes", "1")}"')
        cfg.set('input_libretro_device_p2', f'"{conf.get("controller2_nes", "1")}"')

    elif system == 'psx':
        # DualShock = 517, DigitalController = 1, AnalogJoystick = 513
        for ctrl in ctx.controllers:
            val = conf.get(f'controller{ctrl.player}_psx', '517')
            cfg.set(f'input_libretro_device_p{ctrl.player}', f'"{val}"')

    elif system in ('megadrive',):
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_md", "513")}"')
        cfg.set('input_libretro_device_p2', f'"{conf.get("controller2_md", "513")}"')

    elif system == 'mastersystem':
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_ms", "769")}"')
        cfg.set('input_libretro_device_p2', f'"{conf.get("controller2_ms", "769")}"')

    elif system == 'saturn':
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_saturn", "1")}"')
        cfg.set('input_libretro_device_p2', f'"{conf.get("controller2_saturn", "1")}"')

    elif system in ('pce', 'pcenginecd', 'supergrafx'):
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_pce", "1")}"')

    elif system in ('wii', 'gamecube'):
        cfg.set('input_libretro_device_p1', f'"{conf.get("controller1_wii", "1")}"')


_NETPLAY_MODES: frozenset[str] = frozenset({'host', 'client', 'spectator'})


def _write_retroarch_netplay(cfg: _KVConfig, ctx: LaunchContext) -> None:
    if ctx.netplay_mode not in _NETPLAY_MODES:
        return
    is_client = ctx.netplay_mode in ('client', 'spectator')
    cfg.set('netplay_mode',              '"true"' if is_client else '"false"')
    cfg.set('netplay_ip_port',           f'"{ctx.netplay_port}"')
    cfg.set('netplay_delay_frames',      '"0"')
    cfg.set('netplay_nickname',          f'"{_conf_value(_load_hippos_conf(), "global.netplay.nickname", "")}"')
    cfg.set('netplay_client_swap_input', '"false"')
    if is_client:
        cfg.set('netplay_ip_address', f'"{ctx.netplay_ip}"')
    _log.info("netplay: mode=%s ip=%s port=%s", ctx.netplay_mode, ctx.netplay_ip, ctx.netplay_port)


_REMAPS_DIR = RA_CONFIG_DIR / 'remaps'


def _write_retroarch_remapping(cfg: _KVConfig, ctx: LaunchContext) -> None:
    remap_dir = _REMAPS_DIR / ctx.system
    remap_file = remap_dir / f'{ctx.system}.rmp'
    if not remap_file.exists():
        return
    cfg.set('input_remapping_directory', f'"{remap_dir}"')
    cfg.set('input_remapping_path',      f'"{remap_file}"')
    _log.info("remapping: using %s", remap_file)


_SYSTEMS_NO_REWIND: frozenset[str] = frozenset({
    'sega32x', 'psx', 'zxspectrum', 'n64', 'n64dd',
    'dreamcast', 'atomiswave', 'naomi', 'naomi2', 'saturn',
})


_SYSTEMS_NO_RUNAHEAD: frozenset[str] = frozenset({
    'sega32x', 'n64', 'n64dd', 'dreamcast', 'atomiswave',
    'naomi', 'naomi2', 'saturn',
})


_CORES_FORCE_SLANG: frozenset[str] = frozenset({'mupen64plus_next'})


_RA_DPAD_MAP: list[tuple[str, str]] = [
    ('up',    'up'),
    ('down',  'down'),
    ('left',  'left'),
    ('right', 'right'),
]


_RA_AXIS_MAP: list[tuple[str, str]] = [
    ('joystick1left', 'l_x'),
    ('joystick1up',   'l_y'),
    ('joystick2left', 'r_x'),
    ('joystick2up',   'r_y'),
]


_RA_GUN_BTN_MAP: dict[str, str] = {
    'a':        'aux_a',
    'b':        'aux_b',
    'y':        'aux_c',
    'pageup':   'offscreen_shot',
    'pagedown': 'trigger',
    'start':    'start',
    'select':   'select',
}


def _write_retroarch_controller_bindings(
    cfg: '_KVConfig',
    controllers: list['ControllerInfo'],
    profiles: list['ESControllerProfile'],
    ctx: Optional['LaunchContext'] = None,
) -> None:
    """Write per-player button/axis/hat bindings derived from ES input profiles."""
    system   = ctx.system if ctx else ''
    core     = ctx.core   if ctx else ''
    lightgun = ctx.lightgun if ctx else False
    altlayout = ''
    if ctx:
        conf = _load_hippos_conf()
        altlayout = _conf_value(conf, f'{system}.altlayout', _conf_value(conf, 'global.altlayout', ''))

    for ctrl in controllers:
        n = ctrl.player
        profile = _pick_es_profile(profiles, ctrl)
        if profile is None:
            continue

        btn_map = _ra_btn_map_for_ctx(profile, system, core, altlayout)

        # Buttons and triggers
        for es_name, ra_name in btn_map.items():
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            suffix = _ra_type_suffix(binding)
            cfg.set(f'input_player{n}_{ra_name}_{suffix}', f'"{_ra_binding_value(binding)}"')

        # D-pad — also write gun_dpad_* variants for lightgun systems
        for es_name, ra_name in _RA_DPAD_MAP:
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            suffix = _ra_type_suffix(binding)
            val = f'"{_ra_binding_value(binding)}"'
            cfg.set(f'input_player{n}_{ra_name}_{suffix}', val)
            if lightgun:
                cfg.set(f'input_player{n}_gun_dpad_{ra_name}_{suffix}', val)

        # Lightgun gun button mapping
        if lightgun:
            for es_name, gun_name in _RA_GUN_BTN_MAP.items():
                binding = profile.inputs.get(es_name)
                if binding is None:
                    continue
                suffix = _ra_type_suffix(binding)
                cfg.set(f'input_player{n}_gun_{gun_name}_{suffix}', f'"{_ra_binding_value(binding)}"')

        # Analog sticks: write both ± directions from the single ES directional binding
        for es_name, ra_base in _RA_AXIS_MAP:
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            if binding.type != 'axis':
                continue
            primary_sign  = '-' if binding.value < 0 else '+'
            opposite_sign = '+' if primary_sign == '-' else '-'
            cfg.set(f'input_player{n}_{ra_base}_minus_axis', f'"{primary_sign}{binding.code}"')
            cfg.set(f'input_player{n}_{ra_base}_plus_axis',  f'"{opposite_sign}{binding.code}"')

        # analog_dpad_mode: '1' when dpad is buttons/hats so it also drives the analog stick
        cfg.set(f'input_player{n}_analog_dpad_mode', f'"{_ra_analog_dpad_mode(profile, system)}"')


class _KVConfig:
    """Simple key = value config file (retroarch format)."""

    def __init__(self, path: Path, separator: str = ' ') -> None:
        self.path = path
        self.sep = separator
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            parser = configparser.RawConfigParser()
            parser.optionxform = str  # preserve case
            parser.read_string('[DEFAULT]\n' + self.path.read_text(encoding='latin1'))
            self._data = dict(parser.items('DEFAULT'))
        except Exception as exc:
            _log.warning("Could not read %s: %s", self.path, exc)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def clear_prefix(self, prefix: str) -> None:
        for k in [k for k in self._data if k.startswith(prefix)]:
            del self._data[k]

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('w') as fh:
            for key, value in self._data.items():
                fh.write(f'{key}{self.sep}={self.sep}{value}\n')


def _write_retroarch_config(controllers: list[ControllerInfo], ctx: Optional[LaunchContext] = None) -> Path:
    conf = _load_hippos_conf()
    cfg = _KVConfig(RA_CUSTOM_CFG, separator=' ')

    # Paths
    cfg.set('savefile_directory',       f'"{SAVES}"')
    cfg.set('savestate_directory',      f'"{SAVES}"')
    cfg.set('screenshot_directory',     f'"{SCREENSHOTS}"')
    cfg.set('system_directory',         f'"{BIOS}"')
    cfg.set('core_options_path',        f'"{RA_CORES_CFG}"')
    cfg.set('assets_directory',         '"/usr/share/libretro/assets"')
    cfg.set('video_shader_dir',         f'"{USER_SHADERS}"')
    cfg.set('cheat_database_path',      f'"{CHEATS}"')
    cfg.set('overlay_directory',        f'"{USER_DECORATIONS}"')

    # Video
    cfg.set('video_fullscreen',         '"true"')
    cfg.set('video_threaded',           '"true"' if _conf_bool(conf, 'global.video_threaded') else '"false"')
    cfg.set('video_gpu_screenshot',     '"true"')
    cfg.set('aspect_ratio_index',       f'"{_ratio_index(conf)}"')

    cfg.set('video_smooth',             '"true"' if _conf_bool(conf, 'global.smooth') else '"false"')

    cfg.set('video_scale_integer',      '"true"' if _conf_bool(conf, 'global.integerscale') else '"false"')

    system = ctx.system if ctx is not None else ''
    rewind_ok = system not in _SYSTEMS_NO_REWIND
    cfg.set('rewind_enable', '"true"' if (_conf_bool(conf, 'global.rewind') and rewind_ok) else '"false"')

    runahead = _conf_int(conf, 'global.runahead', 0)
    runahead_ok = system not in _SYSTEMS_NO_RUNAHEAD
    cfg.set('run_ahead_enabled', '"false"')
    cfg.set('preemptive_frames_enable', '"false"')
    cfg.set('run_ahead_frames', '"0"')
    cfg.set('run_ahead_secondary_instance', '"false"')
    if runahead > 0 and runahead_ok:
        if _conf_bool(conf, 'global.preemptiveframes'):
            cfg.set('preemptive_frames_enable', '"true"')
        else:
            cfg.set('run_ahead_enabled', '"true"')
        cfg.set('run_ahead_frames', f'"{runahead}"')
        if _conf_bool(conf, 'global.secondinstance'):
            cfg.set('run_ahead_secondary_instance', '"true"')

    cfg.set('video_frame_delay_auto',   '"true"' if _conf_bool(conf, 'global.video_frame_delay_auto') else '"false"')
    cfg.set('vrr_runloop_enable',       '"true"' if _conf_bool(conf, 'global.vrr_runloop_enable') else '"false"')

    shaderset = conf.get('global.shaderset', 'none').strip()
    core = ctx.core if ctx is not None else ''
    shader_ext = 'slang' if core in _CORES_FORCE_SLANG else 'glslp'
    bezel_path = ctx.bezel if ctx is not None else None
    if bezel_path is not None:
        from hippos_bezels import SHADER_BEZEL, SHADER_BEZEL_DIR
        cfg.set('video_shader_enable', '"true"')
        cfg.set('video_shader_dir',    f'"{SHADER_BEZEL_DIR}"')
        cfg.set('video_shader',        f'"{SHADER_BEZEL}"')
    elif shaderset and shaderset != 'none':
        cfg.set('video_shader_enable', '"true"')
        cfg.set('video_shader', f'"{USER_SHADERS}/{shaderset}.{shader_ext}"')
    else:
        cfg.set('video_shader_enable', '"false"')

    # CRT mode — when switchres.ini is present, enable the switchres resolution
    # switching backend (mode 4) and tune the menu for low-resolution display.
    if Path('/etc/switchres.ini').exists():
        cfg.set('crt_switch_resolution',          '"4"')
        cfg.set('crt_switch_resolution_super',    '"0"')
        cfg.set('menu_driver',                    '"rgui"')
        cfg.set('menu_enable_widgets',            '"false"')
        cfg.set('notification_show_refresh_rate', '"false"')
        cfg.set('video_font_size',                '"10"')

    # Input
    # Autodetect disabled: we write complete explicit per-player bindings from ES
    # profiles. Enabling autodetect causes RetroArch to load its own autoconfig
    # profiles after the config is applied, which overrides our bindings.
    cfg.set('input_autodetect_enable',  '"false"')
    # udev driver reads /dev/input/event* directly — more reliable than sdl2
    # on Debian where SDL2 HIDAPI conflicts with xpad claiming the USB device.
    # Button indices are identical (both enumerate evdev BTN_* codes in order).
    cfg.set('input_joypad_driver',      '"udev"')
    cfg.set('input_enable_hotkey',      '"shift"')
    cfg.set('input_exit_emulator',      '"escape"')
    cfg.set('input_menu_toggle',        '"f1"')
    cfg.set('input_pause_toggle',       '"p"')
    cfg.set('input_save_state',         '"f3"')
    cfg.set('input_load_state',         '"f4"')
    cfg.set('input_screenshot',         '"nul"')
    # Load ES input profiles once — used for hotkey detection and button bindings
    _profiles = _load_es_input_configs()

    # Write the hotkey modifier button index so RetroArch uses the controller button
    # the user configured in ES rather than requiring Shift on keyboard.
    p1 = next((c for c in controllers if c.player == 1), None)
    if p1:
        _profile = _pick_es_profile(_profiles, p1)
        if _profile:
            _hk = _profile.inputs.get('hotkey')
            if _hk and _hk.type == 'button':
                cfg.set('input_enable_hotkey_btn', f'"{_hk.code}"')

    # Clear stale controller keys from any previous launch before rewriting
    cfg.clear_prefix('input_player')

    # Controller port assignments from ES detection
    for ctrl in controllers:
        cfg.set(f'input_player{ctrl.player}_joypad_index', f'"{ctrl.index}"')

    # Per-player button/axis/hat bindings from ES profiles (with system/core-specific remaps)
    _write_retroarch_controller_bindings(cfg, controllers, _profiles, ctx)

    # Libretro device types per core/system
    if ctx is not None:
        _set_libretro_device_types(cfg, ctx, conf)
        _write_retroarch_netplay(cfg, ctx)
        _write_retroarch_remapping(cfg, ctx)

    # Menu / UI
    cfg.set('notification_show_remap_load', '"false"')
    cfg.set('rgui_show_start_screen',   '"false"')
    cfg.set('content_show_favorites',   '"false"')
    cfg.set('content_show_images',      '"false"')
    cfg.set('content_show_music',       '"false"')
    cfg.set('content_show_video',       '"false"')
    cfg.set('content_show_history',     '"false"')
    cfg.set('content_show_playlists',   '"false"')
    cfg.set('menu_show_load_core',      '"false"')
    cfg.set('menu_show_online_updater', '"false"')
    cfg.set('menu_show_core_updater',   '"false"')

    # Save behaviour
    cfg.set('config_save_on_exit',      '"false"')
    cfg.set('log_to_file',              '"true"')
    cfg.set('log_dir',                  f'"{USERDATA / "system" / "logs"}"')
    cfg.set('log_to_file_timestamp',    '"false"')
    cfg.set('savestate_auto_save',      '"true"' if _conf_bool(conf, 'global.autosave') else '"false"')
    cfg.set('savestate_auto_load',      '"true"' if _conf_bool(conf, 'global.autosave') else '"false"')

    # RetroAchievements
    cheevos = _conf_bool(conf, 'global.retroachievements')
    cfg.set('cheevos_enable', '"true"' if cheevos else '"false"')
    if cheevos:
        username = conf.get('global.retroachievements.username', '')
        password = conf.get('global.retroachievements.password', '')
        hardcore = _conf_bool(conf, 'global.retroachievements.hardcore')
        if username:
            cfg.set('cheevos_username', f'"{username}"')
        if password:
            cfg.set('cheevos_password', f'"{password}"')
        cfg.set('cheevos_hardcore_mode_enable', '"true"' if hardcore else '"false"')

    cfg.set('input_rumble_gain', f'"{_conf_value(conf, "global.rumble_gain", "")}"')

    audio_vol = _conf_value(conf, 'global.audio_volume', '0')
    cfg.set('audio_volume', f'"{audio_vol}"')

    ai_enabled = _conf_bool(conf, 'global.ai_service_enabled')
    cfg.set('ai_service_enable', '"true"' if ai_enabled else '"false"')
    if ai_enabled:
        chosen_lang = _conf_value(conf, 'global.ai_target_lang', 'En')
        chosen_url = _conf_value(conf, 'global.ai_service_url', 'http://ztranslate.net/service?api_key=BATOCERA')
        cfg.set('ai_service_mode', '"0"')
        cfg.set('ai_service_source_lang', '"0"')
        cfg.set('ai_service_url', f'"{chosen_url}&mode=Fast&output=png&target_lang={chosen_lang}"')
        cfg.set('ai_service_pause', '"true"' if _conf_bool(conf, 'global.ai_service_pause') else '"false"')

    cfg.write()
    _log.info("Wrote retroarch config: %s", RA_CUSTOM_CFG)
    return RA_CUSTOM_CFG


def _write_retroarch_core_options(ctx: LaunchContext, conf: dict[str, str]) -> None:
    """Write per-core settings to retroarch-core-options.cfg."""
    RA_CORES_CFG.parent.mkdir(parents=True, exist_ok=True)
    opts: dict[str, str] = {}

    def _get(key: str, default: str = '') -> str:
        return conf.get(f'{ctx.system}.{key}') or conf.get(f'global.{key}', default)

    core = ctx.core

    if core in ('stella', 'stella2014'):
        opts['stella_console']             = _get('stella_console', 'auto')
        opts['stella_palette']             = _get('stella_palette', 'standard')
        opts['stella_filter']              = _get('stella_filter', 'disabled')
        opts['stella_crop_hoverscan']      = _get('stella_crop_hoverscan', 'disabled')
        opts['stella_ntsc_aspect']         = _get('stella_ntsc_aspect', 'par')
        opts['stella_phosphor']            = _get('stella_phosphor', 'auto')
        opts['stella_phosphor_blend']      = _get('stella_phosphor_blend', '60')

    elif core in ('snes9x', 'snes9x_next', 'bsnes', 'bsnes_mercury_balanced'):
        opts['snes9x_gfx_hires']          = _get('snes9x_gfx_hires', 'enabled')
        opts['snes9x_overscan']            = _get('snes9x_overscan', 'enabled')
        opts['snes9x_aspect']              = _get('snes9x_aspect', '4:3')
        opts['snes9x_region']              = _get('snes9x_region', 'auto')

    elif core in ('mgba',):
        opts['mgba_gb_model']             = _get('mgba_gb_model', 'Autodetect')
        opts['mgba_sgb_borders']          = _get('mgba_sgb_borders', 'ON')
        opts['mgba_frameskip']            = _get('mgba_frameskip', '0')
        opts['mgba_color_correction']     = _get('mgba_color_correction', 'OFF')

    elif core in ('gambatte',):
        opts['gambatte_gb_colorization']  = _get('gambatte_gb_colorization', 'disabled')
        opts['gambatte_gb_internal_palette'] = _get('gambatte_gb_internal_palette', 'GB - DMG')
        opts['gambatte_mix_frames']       = _get('gambatte_mix_frames', 'disabled')

    elif core in ('genesisplusgx', 'genesis_plus_gx', 'genesis_plus_gx_wide'):
        opts['genesis_plus_gx_system_hw'] = _get('genesis_plus_gx_system_hw', 'auto')
        opts['genesis_plus_gx_region_detect'] = _get('genesis_plus_gx_region_detect', 'auto')
        opts['genesis_plus_gx_aspect_ratio']  = _get('genesis_plus_gx_aspect_ratio', 'auto')
        opts['genesis_plus_gx_render']        = _get('genesis_plus_gx_render', 'single field')

    elif core in ('fceumm',):
        opts['fceumm_region']             = _get('fceumm_region', 'Auto')
        opts['fceumm_overscan']           = _get('fceumm_overscan', 'enabled')
        opts['fceumm_palette']            = _get('fceumm_palette', 'default')

    elif core in ('mesen',):
        opts['mesen_region']              = _get('mesen_region', 'Auto')
        opts['mesen_overscan_left']       = _get('mesen_overscan_left', '0')
        opts['mesen_overscan_right']      = _get('mesen_overscan_right', '0')
        opts['mesen_overscan_top']        = _get('mesen_overscan_top', '8')
        opts['mesen_overscan_bottom']     = _get('mesen_overscan_bottom', '8')

    elif core in ('beetle_pce', 'beetle_pce_fast'):
        opts['pce_cdimagedir']            = ''
        opts['pce_nospritelimit']         = _get('pce_nospritelimit', 'disabled')
        opts['pce_ocmultiplier']          = _get('pce_ocmultiplier', '1')
        opts['pce_aspect_ratio']          = _get('pce_aspect_ratio', 'auto')

    elif core in ('mame', 'mame2003_plus'):
        opts['mame_read_config']          = _get('mame_read_config', 'disabled')
        opts['mame_write_config']         = _get('mame_write_config', 'disabled')
        opts['mame_boot_to_bios']         = _get('mame_boot_to_bios', 'disabled')
        opts['mame_softlists_enable']     = _get('mame_softlists_enable', 'enabled')
        opts['mame_softlists_auto_media'] = _get('mame_softlists_auto_media', 'enabled')
        opts['mame_media_type']           = _get('mame_media_type', 'rom')

    elif core in ('fbneo', 'fbalpha'):
        opts['fbneo-lightgun-hide-crosshair'] = _get('fbneo_hide_crosshair', 'enabled')
        opts['fbneo-allow-patched-romsets']   = _get('fbneo_patched_roms', 'enabled')

    elif core in ('atari800', 'a5200'):
        if ctx.system == 'atari800':
            opts['atari800_system']       = _get('atari800_system', '800XL (64K)')
            opts['atari800_ntscpal']      = _get('atari800_ntscpal', 'NTSC')
            opts['atari800_sioaccel']     = _get('atari800_sioaccel', 'enabled')
        else:
            opts['atari800_system']       = '5200'
            opts['atari800_CartType']     = 'enabled'

    elif core in ('mupen64plus_next', 'parallel_n64'):
        opts['mupen64plus-rdp-plugin']    = _get('mupen64plus_rdp', 'gliden64')
        opts['mupen64plus-rsp-plugin']    = _get('mupen64plus_rsp', 'hle')
        opts['mupen64plus-43screensize']  = _get('mupen64plus_screensize', '640x480')
        opts['mupen64plus-169screensize'] = _get('mupen64plus_169screensize', '854x480')

    if not opts:
        return

    # Read existing options and merge (preserve user overrides)
    existing: dict[str, str] = {}
    if RA_CORES_CFG.exists():
        try:
            for line in RA_CORES_CFG.read_text().splitlines():
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, _, v = line.partition('=')
                    existing[k.strip()] = v.strip().strip('"')
        except OSError:
            pass

    # Only write defaults — don't overwrite user-set values
    for k, v in opts.items():
        if k not in existing:
            existing[k] = v

    lines = [f'{k} = "{v}"' for k, v in sorted(existing.items())]
    RA_CORES_CFG.write_text('\n'.join(lines) + '\n')
    _log.info("core options: wrote %d entries for core '%s'", len(opts), core)


def _write_retroarch_game_overrides(ctx: LaunchContext) -> Optional[Path]:
    if not ctx.lightgun and not ctx.wheel:
        return None

    cfg = _KVConfig(Path(f'/tmp/hippos-retroarch-{os.getpid()}-override.cfg'), separator=' ')

    if ctx.lightgun:
        for ctrl in ctx.controllers:
            cfg.set(f'input_player{ctrl.player}_mouse_index', '"0"')
        if ctx.core == 'nestopia':
            cfg.set('nestopia_zapper_device', '"lightgun"')
        elif ctx.core == 'fceux':
            cfg.set('fceumm_zapper_mode', '"lightgun"')
        elif ctx.core == 'mame2003-plus':
            cfg.set('mame2003-plus_xy_device', '"lightgun"')
        elif ctx.core == 'genesis_plus_gx':
            cfg.set('genesis_plus_gx_gun_input', '"lightgun"')
        elif ctx.core == 'stella':
            cfg.set('stella_lightgun_crosshair', '"enabled"')
        elif ctx.core == 'reicast':
            cfg.set('reicast_lightgun1_crosshair', '"Red"')
            cfg.set('reicast_lightgun2_crosshair', '"Blue"')
            cfg.set('reicast_lightgun3_crosshair', '"Green"')
            cfg.set('reicast_lightgun4_crosshair', '"White"')
        elif ctx.core == 'fbneo':
            cfg.set('fbneo-lightgun-crosshair-emulation', '"always show"')
        elif ctx.core == 'bsnes':
            cfg.set('bsnes_touchscreen_lightgun_superscope_reverse', '"OFF"')

    if ctx.wheel:
        if ctx.core in ('mupen64plus', 'mupen64plus_next', 'parallel_n64'):
            cfg.set('mupen64plus-astick-deadzone', '"0"')
            cfg.set('parallel-n64-astick-deadzone', '"0"')
        if ctx.core == 'reicast':
            cfg.set('reicast_analog_stick_deadzone', '"0%"')
        if ctx.core == 'beetle-saturn':
            cfg.set('beetle_saturn_analog_stick_deadzone', '"0%"')

    cfg.write()
    _log.info("Wrote retroarch overrides: %s", cfg.path)
    return cfg.path
