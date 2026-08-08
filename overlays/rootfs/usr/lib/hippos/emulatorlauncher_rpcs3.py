from __future__ import annotations

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

from emulatorlauncher_shared import (
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
    _run_game_command,
)

from HipposPaths import CACHE, CONFIGS, SAVES


RPCS3_CONFIG_DIR   = CONFIGS / 'rpcs3'
RPCS3_CONFIG_YML   = RPCS3_CONFIG_DIR / 'config.yml'


_RPCS3_INPUT_DIR = RPCS3_CONFIG_DIR / 'input_configs' / 'global'

_RPCS3_SONY_GUIDS: frozenset[str] = frozenset({
    # DS3
    '030000004c0500006802000011010000', '030000004c0500006802000011810000',
    '050000004c0500006802000000800000', '050000004c0500006802000000000000',
    # DS4
    '030000004c050000c405000011810000', '050000004c050000c405000000810000',
    '030000004c050000cc09000011010000', '050000004c050000cc09000000010000',
    '030000004c050000cc09000011810000', '050000004c050000cc09000000810000',
    '030000004c050000a00b000011010000', '030000004c050000a00b000011810000',
    # DS5
    '030000004c050000e60c000011810000', '050000004c050000e60c000000810000',
})
_RPCS3_EVDEV_MAP = [
    ('up',          'Up',              'BTN_DPAD_UP',   'ABS_HAT0Y', 'Hat0 Y-'),
    ('down',        'Down',            'BTN_DPAD_DOWN', 'ABS_HAT0Y', 'Hat0 Y+'),
    ('left',        'Left',            'BTN_DPAD_LEFT', 'ABS_HAT0X', 'Hat0 X-'),
    ('right',       'Right',           'BTN_DPAD_RIGHT','ABS_HAT0X', 'Hat0 X+'),
    ('l2',          'L2',              'BTN_TL2',       'ABS_Z',     'LZ+'),
    ('r2',          'R2',              'BTN_TR2',       'ABS_RZ',    'RZ+'),
    ('a',           'Cross',           'BTN_A',         None,        None),
    ('b',           'Circle',          'BTN_B',         None,        None),
    ('x',           'Square',          'BTN_X',         None,        None),
    ('y',           'Triangle',        'BTN_Y',         None,        None),
    ('joystick1up', 'Left Stick Up',   None,            'ABS_Y',     'LY-'),
    ('joystick1left','Left Stick Left',None,            'ABS_X',     'LX-'),
    ('joystick2up', 'Right Stick Up',  None,            'ABS_RY',    'RY-'),
    ('joystick2left','Right Stick Left',None,           'ABS_RX',    'RX-'),
]


def _write_rpcs3_config(conf: dict[str, str]) -> None:
    """Write RPCS3 config.yml from hippos.conf values.

    RPCS3 uses YAML format. We use the yaml module if available,
    otherwise write raw YAML text.
    """
    RPCS3_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if _HAS_YAML and RPCS3_CONFIG_YML.exists():
        try:
            existing = yaml.safe_load(RPCS3_CONFIG_YML.read_text()) or {}
        except Exception:
            existing = {}

    # Ensure top-level keys exist
    for key in ('Core', 'Video', 'Audio', 'Input/Output', 'Miscellaneous'):
        if key not in existing:
            existing[key] = {}

    # Core
    existing['Core']['PPU Decoder']           = _conf_value(conf, 'global.rpcs3_ppudecoder', 'Recompiler (LLVM)')
    existing['Core']['SPU Decoder']           = _conf_value(conf, 'global.rpcs3_spudecoder', 'Recompiler (LLVM)')
    existing['Core']['XFloat Accuracy']       = _conf_value(conf, 'global.rpcs3_spuxfloataccuracy', 'Approximate')
    existing['Core']['SPU Cache']             = True
    existing['Core']['Preferred SPU Threads'] = _conf_int(conf, 'global.rpcs3_sputhreads', 0)
    existing['Core']['SPU loop detection']    = _conf_bool(conf, 'global.rpcs3_spuloopdetection', False)
    existing['Core']['SPU Block Size']        = _conf_value(conf, 'global.rpcs3_spublocksize', 'Safe')
    existing['Core']['Sleep Timers Accuracy'] = _conf_value(conf, 'global.rpcs3_sleep_timers_accuracy', 'As Host')

    # Video
    gfxbackend = _conf_value(conf, 'global.rpcs3_gfxbackend', '')
    existing['Video']['Renderer']          = 'OpenGL' if gfxbackend == 'OpenGL' else 'Vulkan'
    ratio = _conf_value(conf, 'global.rpcs3_ratio', '')
    existing['Video']['Aspect ratio']      = ratio if ratio else '16:9'
    existing['Video']['Shader Mode']       = _conf_value(conf, 'global.rpcs3_shadermode', 'Async Shader Recompiler')
    existing['Video']['VSync']             = _conf_bool(conf, 'global.rpcs3_vsync', False)
    existing['Video']['Stretch To Display Area'] = _conf_bool(conf, 'global.rpcs3_stretchdisplay', False)
    existing['Video']['Write Color Buffers'] = _conf_bool(conf, 'global.rpcs3_colorbuffers', False)
    existing['Video']['Disable Vertex Cache'] = _conf_bool(conf, 'global.rpcs3_vertexcache', False)
    existing['Video']['Anisotropic Filter Override'] = _conf_int(conf, 'global.rpcs3_anisotropic', 0)
    existing['Video']['MSAA']             = _conf_value(conf, 'global.rpcs3_aa', 'Auto')
    existing['Video']['Shader Precision'] = _conf_value(conf, 'global.rpcs3_shader', 'High')
    existing['Video']['Resolution']       = '1280x720'
    existing['Video']['Resolution Scale'] = _conf_int(conf, 'global.rpcs3_resolution_scale', 100)
    existing['Video']['Output Scaling Mode'] = _conf_value(conf, 'global.rpcs3_scaling', 'Bilinear')
    existing['Video']['Shader Compiler Threads'] = _conf_int(conf, 'global.rpcs3_num_compilers', 0)
    existing['Video']['Multithreaded RSX'] = _conf_bool(conf, 'global.rpcs3_rsx', False)
    existing['Video']['Asynchronous Texture Streaming 2'] = _conf_bool(conf, 'global.rpcs3_async_texture', False)
    existing['Video']['Write Depth Buffer'] = _conf_bool(conf, 'global.rpcs3_write_depth_buffers', False)
    framelimit = _conf_value(conf, 'global.rpcs3_framelimit', '')
    if not framelimit:
        existing['Video']['Frame limit'] = 'Auto'
        existing['Video']['Second Frame Limit'] = 0
    elif framelimit in ('Off', '30', '50', '59.94', '60'):
        existing['Video']['Frame limit'] = framelimit
        existing['Video']['Second Frame Limit'] = 0
    else:
        existing['Video']['Frame limit'] = 'Off'
        try:
            existing['Video']['Second Frame Limit'] = float(framelimit)
        except ValueError:
            existing['Video']['Second Frame Limit'] = 0

    # Audio
    existing['Audio']['Renderer']          = 'Cubeb'
    existing['Audio']['Master Volume']     = 100
    existing['Audio']['Enable Buffering']  = _conf_bool(conf, 'global.rpcs3_audiobuffer', True)
    existing['Audio']['Desired Audio Buffer Duration'] = _conf_int(conf, 'global.rpcs3_audiobuffer_duration', 100)
    if _conf_bool(conf, 'global.rpcs3_timestretch', False):
        existing['Audio']['Enable Time Stretching'] = True
        existing['Audio']['Enable Buffering']       = True
    else:
        existing['Audio']['Enable Time Stretching'] = False

    # Miscellaneous
    existing['Miscellaneous']['Exit RPCS3 when process finishes']  = True
    existing['Miscellaneous']['Start games in fullscreen mode']    = True
    existing['Miscellaneous']['Show shader compilation hint']      = False
    existing['Miscellaneous']['Prevent display sleep while running games'] = True
    existing['Miscellaneous']['Show trophy popups']                = False

    if _HAS_YAML:
        RPCS3_CONFIG_YML.write_text(yaml.dump(existing, default_flow_style=False, allow_unicode=True))
    else:
        # Fallback: write minimal YAML without lists
        lines = ['---']
        for section, items in existing.items():
            lines.append(f'{section}:')
            if isinstance(items, dict):
                for k, v in items.items():
                    if isinstance(v, bool):
                        lines.append(f'  {k}: {str(v).lower()}')
                    else:
                        lines.append(f'  {k}: {v}')
        RPCS3_CONFIG_YML.write_text('\n'.join(lines) + '\n')

    _log.info("Wrote RPCS3 config: %s", RPCS3_CONFIG_YML)


def _write_rpcs3_controller_config(ctx: LaunchContext) -> None:
    """Write RPCS3 Default.yml input config."""
    _RPCS3_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    conf      = _load_hippos_conf()
    profiles  = _load_es_input_configs()
    ds3_count = ds4_count = ds5_count = 1

    config_path = _RPCS3_INPUT_DIR / 'Default.yml'
    with config_path.open('w', encoding='utf-8-sig') as f:
        for nplayer, ctrl in enumerate(ctx.controllers[:7], start=1):
            guid = ctrl.guid.lower()
            ctrl_type = conf.get(f'rpcs3_controller{nplayer}', '')
            rumble    = 'false' if not _conf_bool(conf, f'rpcs3_rumble{nplayer}', True) else 'true'

            if guid in _RPCS3_SONY_GUIDS and ctrl_type == 'Sony':
                # Sony native handler
                ds3_guids = list(_RPCS3_SONY_GUIDS)[:4]
                ds4_guids = list(_RPCS3_SONY_GUIDS)[4:12]
                if guid in ds3_guids:
                    f.write(f'Player {nplayer} Input:\n')
                    f.write('  Handler: DualShock 3\n')
                    f.write(f'  Device: "DS3 Pad #{ds3_count}"\n')
                    ds3_count += 1
                elif guid in ds4_guids:
                    f.write(f'Player {nplayer} Input:\n')
                    f.write('  Handler: DualShock 4\n')
                    f.write(f'  Device: "DS4 Pad #{ds4_count}"\n')
                    ds4_count += 1
                else:
                    f.write(f'Player {nplayer} Input:\n')
                    f.write('  Handler: DualSense\n')
                    f.write(f'  Device: "DualSense Pad #{ds5_count}"\n')
                    ds5_count += 1
                f.write('  Config:\n')
                for line in (
                    '    Left Stick Left: LS X-',  '    Left Stick Down: LS Y-',
                    '    Left Stick Right: LS X+', '    Left Stick Up: LS Y+',
                    '    Right Stick Left: RS X-', '    Right Stick Down: RS Y-',
                    '    Right Stick Right: RS X+','    Right Stick Up: RS Y+',
                    '    Start: Options',           '    Select: Share',
                    '    PS Button: PS Button',     '    Square: Square',
                    '    Cross: Cross',             '    Circle: Circle',
                    '    Triangle: Triangle',       '    Left: Left',
                    '    Down: Down',               '    Right: Right',
                    '    Up: Up',                   '    R1: R1',
                    '    R2: R2',                   '    R3: R3',
                    '    L1: L1',                   '    L2: L2',
                    '    L3: L3',
                    '    Left Stick Deadzone: 40',  '    Right Stick Deadzone: 40',
                    '    Left Trigger Threshold: 0','    Right Trigger Threshold: 0',
                    '    Left Stick Multiplier: 100','    Right Stick Multiplier: 100',
                    f'    Enable Large Vibration Motor: {rumble}',
                    f'    Enable Small Vibration Motor: {rumble}',
                ):
                    f.write(line + '\n')
                f.write('  Buddy Device: ""\n')

            else:
                # Evdev handler — maps ES inputs to evdev event names
                profile = _pick_es_profile(profiles, ctrl)
                f.write(f'Player {nplayer} Input:\n')
                f.write('  Handler: Evdev\n')
                f.write(f'  Device: {ctrl.device_path or "/dev/input/js0"}\n')
                f.write('  Config:\n')
                f.write('    Start: Start\n')
                f.write('    Select: Select\n')
                f.write('    PS Button: Mode\n')

                if profile is not None:
                    for es_name, cfg_name, btn_evt, axis_evt, axis_val in _RPCS3_EVDEV_MAP:
                        binding = profile.inputs.get(es_name)
                        if binding is None:
                            continue
                        if binding.type == 'button' and btn_evt:
                            f.write(f'    {cfg_name}: {btn_evt.replace("BTN_", "").capitalize()}\n')
                        elif binding.type in ('hat', 'axis') and axis_evt and axis_val:
                            f.write(f'    {cfg_name}: {axis_val}\n')

                f.write('    Left Stick Deadzone: 30\n')
                f.write('    Right Stick Deadzone: 30\n')
                f.write(f'    Enable Large Vibration Motor: {rumble}\n')
                f.write(f'    Enable Small Vibration Motor: {rumble}\n')
                f.write('  Buddy Device: ""\n')

    _log.info("Wrote RPCS3 controller config: %s", config_path)


def launch_rpcs3(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('rpcs3')
    if bin_path is None:
        _log.error("rpcs3 not found")
        return 1
    (SAVES / 'ps3').mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_rpcs3_config(conf)
    _write_rpcs3_controller_config(ctx)
    # Determine ROM path
    rom = ctx.rom
    if rom.suffix.lower() == '.ink':
        # .ink shortcut: text file containing path to PS3 game directory
        try:
            target = Path(rom.read_text().strip())
            if target.is_dir():
                rom = target / 'PS3_GAME' / 'USRDIR' / 'EBOOT.BIN'
            else:
                rom = target
        except Exception:
            pass
    if rom.suffix == '.psn':
        game_id = None
        try:
            for line in rom.read_text().splitlines():
                if len(line) >= 9:
                    game_id = line.strip().upper()
        except Exception:
            pass
        if game_id:
            eboot = RPCS3_CONFIG_DIR / 'dev_hdd0' / 'game' / game_id / 'USRDIR' / 'EBOOT.BIN'
            rom = eboot
    elif rom.is_dir():
        rom = rom / 'PS3_GAME' / 'USRDIR' / 'EBOOT.BIN'
    cmd = [str(bin_path), '--no-gui', str(rom)]
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_CACHE_HOME']  = str(CACHE)
    result = _run_game_command(ctx, 'rpcs3', cmd, env)
    return result.returncode
