from __future__ import annotations

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _ensure_section,
    _find_emulator_bin,
    _load_es_input_configs,
    _load_hippos_conf,
    _log,
    _new_ini_parser,
    _pick_es_profile,
    _run_game_command,
    generate_sdl_game_controller_config,
)

from HipposPaths import CONFIGS, SAVES


PPSSPP_CONFIG_DIR    = CONFIGS / 'ppsspp'
PPSSPP_INI           = PPSSPP_CONFIG_DIR / 'PSP' / 'SYSTEM' / 'ppsspp.ini'
PPSSPP_CONTROLS_INI  = PPSSPP_CONFIG_DIR / 'PSP' / 'SYSTEM' / 'controls.ini'


_PPSSPP_NKCODE = {
    'b':        189,  # A  → Circle
    'a':        190,  # B  → Cross
    'y':        191,  # X  → Triangle (note: ES y = Square label, PPSSPP Triangle)
    'x':        188,  # Y  → Square
    'select':   196,  # Select/Back
    'start':    197,  # Start
    'pageup':   193,  # L
    'pagedown': 192,  # R
    'up':        19,
    'down':      20,
    'left':      21,
    'right':     22,
}
_PPSSPP_HAT_DIR = {1: 19, 2: 22, 4: 20, 8: 21}  # SDL hat bitmask → NKCODE
_PPSSPP_AXIS_ID = {0: 0, 1: 1, 2: 11, 3: 14, 4: 17, 5: 18}  # SDL axis → PPSSPP axis
_PPSSPP_AXIS_BASE = 4000
_PPSSPP_DEVICE_BASE = 10  # DEVICE_ID_PAD_0

_PPSSPP_BTN_MAP: dict[str, str] = {
    'a': 'Circle', 'b': 'Cross', 'x': 'Triangle', 'y': 'Square',
    'start': 'Start', 'select': 'Select',
    'pageup': 'L', 'pagedown': 'R',
    'up': 'Up', 'down': 'Down', 'left': 'Left', 'right': 'Right',
}
_PPSSPP_AXIS_MAP: dict[str, tuple[str, str]] = {
    'joystick1left':  ('An.Left',       'An.Right'),
    'joystick1up':    ('An.Up',         'An.Down'),
    'joystick2left':  ('RightAn.Left',  'RightAn.Right'),
    'joystick2up':    ('RightAn.Up',    'RightAn.Down'),
}


def _write_ppsspp_config(conf: dict[str, str]) -> None:
    """Write PPSSPP INI config from hippos.conf values."""
    PPSSPP_INI.parent.mkdir(parents=True, exist_ok=True)
    parser = _new_ini_parser()
    if PPSSPP_INI.exists():
        parser.read(PPSSPP_INI, encoding='utf-8')

    for section in ('Graphics', 'SystemParam', 'General', 'Upgrade'):
        _ensure_section(parser, section)

    # Graphics section
    parser.set('Graphics', 'GraphicsBackend',     _conf_value(conf, 'global.gfxbackend', '0 (OPENGL)'))
    parser.set('Graphics', 'InternalResolution',  _conf_value(conf, 'global.internal_resolution', '1'))
    parser.set('Graphics', 'SoftwareRenderer',    'False')
    parser.set('Graphics', 'FullScreen',          'True')
    vsync_val = _conf_value(conf, 'global.vsync', '0')
    parser.set('Graphics', 'VSync',               'True' if vsync_val == '1' else 'False')
    parser.set('Graphics', 'FrameSkip',           _conf_value(conf, 'global.frameskip', '0'))
    parser.set('Graphics', 'FrameSkipType',       '0')
    autoframeskip = _conf_value(conf, 'global.autoframeskip', '0')
    parser.set('Graphics', 'AutoFrameSkip',       'True' if autoframeskip == '1' else 'False')
    skip_buf = _conf_value(conf, 'global.skip_buffer_effects', 'False')
    parser.set('Graphics', 'SkipBufferEffects',   'True' if skip_buf == 'True' else 'False')
    cull = _conf_value(conf, 'global.disable_culling', '0')
    parser.set('Graphics', 'DisableRangeCulling', 'True' if cull == '1' else 'False')
    parser.set('Graphics', 'SkipGPUReadbackMode', _conf_value(conf, 'global.skip_gpu_readbacks', '0'))
    lazy = _conf_value(conf, 'global.lazy_texture_caching', '0')
    parser.set('Graphics', 'TextureBackoffCache', 'True' if lazy == '1' else 'False')
    parser.set('Graphics', 'SplineBezierQuality', _conf_value(conf, 'global.curves_quality', '2'))
    dup = _conf_value(conf, 'global.duplicate_frames', '0')
    parser.set('Graphics', 'RenderDuplicateFrames', 'True' if dup == '1' else 'False')
    parser.set('Graphics', 'InflightFrames',      _conf_value(conf, 'global.buffer_graphics', '3'))
    parser.set('Graphics', 'HardwareTransform',   'True')
    sw_skin = _conf_value(conf, 'global.software_skinning', '1')
    parser.set('Graphics', 'SoftwareSkinning',    'True' if sw_skin == '1' else 'False')
    hw_tess = _conf_value(conf, 'global.hardware_tessellation', '0')
    parser.set('Graphics', 'HardwareTessellation', 'True' if hw_tess == '1' else 'False')
    parser.set('Graphics', 'TexScalingType',      _conf_value(conf, 'global.texture_scaling_type', '0'))
    parser.set('Graphics', 'TexScalingLevel',     _conf_value(conf, 'global.texture_scaling_level', '1'))
    deposterize = _conf_value(conf, 'global.texture_deposterize', 'False')
    parser.set('Graphics', 'TexDeposterize',      'True' if deposterize == 'True' else 'False')
    parser.set('Graphics', 'AnisotropyLevel',     _conf_value(conf, 'global.anisotropic_filtering', '4'))
    parser.set('Graphics', 'TextureFiltering',    _conf_value(conf, 'global.texture_filtering', '1'))
    smart2d = _conf_value(conf, 'global.smart_2d', 'False')
    parser.set('Graphics', 'Smart2DTexFiltering', 'True' if smart2d == 'True' else 'False')
    parser.set('Graphics', 'DisplayIntegerScale', 'False')

    # SystemParam section
    parser.set('SystemParam', 'NickName',     'HippOS')
    parser.set('SystemParam', 'EncryptSave',  'False')
    parser.set('SystemParam', 'MemStickSize', '32')

    # General section
    parser.set('General', 'FirstRun',            'False')
    rewind = _conf_bool(conf, 'global.rewind')
    parser.set('General', 'RewindFlipFrequency', '300' if rewind else '0')
    cheats = _conf_value(conf, 'global.enable_cheats', 'False')
    parser.set('General', 'EnableCheats',        'True' if cheats == 'True' else 'False')
    parser.set('General', 'CheckForNewVersion',  'False')

    # Upgrade section - suppress update prompts
    parser.set('Upgrade', 'UpgradeMessage',   '')
    parser.set('Upgrade', 'UpgradeVersion',   '')
    parser.set('Upgrade', 'DismissedVersion', '')

    with PPSSPP_INI.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote PPSSPP config: %s", PPSSPP_INI)


def _ppsspp_axis_code(axis_id: int, direction: int) -> int:
    d = 1 if direction < 0 else 0
    return _PPSSPP_AXIS_BASE + axis_id * 2 + d


def _write_ppsspp_controls(ctx: LaunchContext) -> None:
    """Write PPSSPP controls.ini from the connected P1 ES controller profile."""
    PPSSPP_CONTROLS_INI.parent.mkdir(parents=True, exist_ok=True)
    profiles = _load_es_input_configs()
    p1 = next((c for c in ctx.controllers if c.player == 1), None)
    if p1 is None:
        return
    profile = _pick_es_profile(profiles, p1)
    if profile is None:
        return

    device_id = _PPSSPP_DEVICE_BASE + p1.index
    section = 'ControlMapping'

    parser = _new_ini_parser()
    _ensure_section(parser, section)

    def _append(key: str, val: str) -> None:
        existing = parser.get(section, key, fallback='')
        parser.set(section, key, f'{existing},{val}' if existing else val)

    # Buttons
    for es_name, ppsspp_name in _PPSSPP_BTN_MAP.items():
        binding = profile.inputs.get(es_name)
        if binding is None:
            continue
        if binding.type == 'button':
            nk = _PPSSPP_NKCODE.get(es_name)
            if nk is not None:
                _append(ppsspp_name, f'{device_id}-{nk}')
        elif binding.type == 'hat':
            nk = _PPSSPP_HAT_DIR.get(abs(binding.value))
            if nk is not None:
                _append(ppsspp_name, f'{device_id}-{nk}')
        elif binding.type == 'axis':
            raw_id = _PPSSPP_AXIS_ID.get(binding.code, binding.code)
            code = _ppsspp_axis_code(raw_id, binding.value)
            _append(ppsspp_name, f'{device_id}-{code}')

    # Analog sticks
    for es_name, (ppsspp_neg, ppsspp_pos) in _PPSSPP_AXIS_MAP.items():
        binding = profile.inputs.get(es_name)
        if binding is None or binding.type != 'axis':
            continue
        raw_id = _PPSSPP_AXIS_ID.get(binding.code, binding.code)
        neg_code = _ppsspp_axis_code(raw_id, -1)
        pos_code = _ppsspp_axis_code(raw_id, 1)
        _append(ppsspp_neg, f'{device_id}-{neg_code}')
        _append(ppsspp_pos, f'{device_id}-{pos_code}')

    # Hotkeys (keyboard bindings for F-keys)
    parser.set(section, 'Rewind',        '1-131')
    parser.set(section, 'Fast-forward',  '1-132')
    parser.set(section, 'Save State',    '1-133')
    parser.set(section, 'Load State',    '1-134')
    parser.set(section, 'Previous Slot', '1-135')
    parser.set(section, 'Next Slot',     '1-136')
    parser.set(section, 'Screenshot',    '1-137')
    parser.set(section, 'Pause',         '1-139')

    with PPSSPP_CONTROLS_INI.open('w', encoding='utf-8') as fh:
        parser.write(fh)
    _log.info("Wrote PPSSPP controls: %s", PPSSPP_CONTROLS_INI)


def launch_ppsspp(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('ppsspp')
    if bin_path is None:
        _log.error("ppsspp not found")
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_ppsspp_config(conf)
    _write_ppsspp_controls(ctx)
    # --fullscreen and SDL_GAMECONTROLLERCONFIG without hotkey
    cmd = [str(bin_path), '--fullscreen', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    # PPSSPP uses hotkey button as menu toggle — exclude it from SDL mapping
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(
        ctx.controllers, ignore_buttons=['hotkey']
    )
    result = _run_game_command(ctx, 'ppsspp', cmd, env)
    return result.returncode
