from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from emulatorlauncher_shared import (
    ESControllerProfile,
    LaunchContext,
    _build_game_env,
    _conf_value,
    _find_emulator_bin,
    _load_es_input_configs,
    _load_hippos_conf,
    _log,
    _pick_es_profile,
    _run_game_command,
)

from HipposPaths import CONFIGS

DRASTIC_HOME = CONFIGS / 'drastic'
DRASTIC_CFG = DRASTIC_HOME / 'config' / 'drastic.cfg'

UNBOUND = '65535'
JOY_BUTTON = 1024
JOY_HAT = 1088
JOY_AXIS_POSITIVE = 1152
JOY_AXIS_NEGATIVE = 1216
KEY_SCANCODE = 256

SCANCODE_F1 = 58
SCANCODE_F2 = 59
SCANCODE_F5 = 62
SCANCODE_F7 = 64
ASCII_TAB = 9

HOTKEY_CONTROLS = {
    'controls_a[CONTROL_INDEX_MENU]': str(KEY_SCANCODE + SCANCODE_F1),
    'controls_a[CONTROL_INDEX_SWAP_SCREENS]': str(KEY_SCANCODE + SCANCODE_F2),
    'controls_a[CONTROL_INDEX_SAVE_STATE]': str(KEY_SCANCODE + SCANCODE_F5),
    'controls_a[CONTROL_INDEX_LOAD_STATE]': str(KEY_SCANCODE + SCANCODE_F7),
    'controls_a[CONTROL_INDEX_FAST_FORWARD]': str(ASCII_TAB),
}

PAD_CONTROLS = {
    'UP': 'up', 'DOWN': 'down', 'LEFT': 'left', 'RIGHT': 'right',
    'A': 'a', 'B': 'b', 'X': 'x', 'Y': 'y',
    'L': 'pageup', 'R': 'pagedown', 'START': 'start', 'SELECT': 'select',
    'SWAP_SCREENS': 'l2', 'FAST_FORWARD': 'r2',
    'TOUCH_CURSOR_PRESS': 'l3', 'MENU': 'r3',
    'UI_UP': 'up', 'UI_DOWN': 'down', 'UI_LEFT': 'left', 'UI_RIGHT': 'right',
    'UI_SELECT': 'a', 'UI_BACK': 'x', 'UI_EXIT': 'b', 'UI_SWITCH': 'y',
    'UI_PAGE_UP': 'pagedown', 'UI_PAGE_DOWN': 'pageup',
}

def _drastic_code(profile: ESControllerProfile, es_name: str) -> str:
    binding = profile.inputs.get(es_name)
    if binding is None:
        return UNBOUND
    if binding.type == 'button':
        return str(JOY_BUTTON + binding.code)
    if binding.type == 'hat':
        return str(JOY_HAT + binding.value)
    return UNBOUND

def _pad_controls(profile: Optional[ESControllerProfile]) -> dict[str, str]:
    if profile is None:
        return {}
    controls = {f'controls_b[CONTROL_INDEX_{name}]': _drastic_code(profile, es_name)
                for name, es_name in PAD_CONTROLS.items()}
    x_axis = profile.inputs.get('joystick1left')
    y_axis = profile.inputs.get('joystick1up')
    if x_axis is not None and y_axis is not None:
        controls['controls_b[CONTROL_INDEX_TOUCH_CURSOR_LEFT]'] = str(JOY_AXIS_NEGATIVE + x_axis.code)
        controls['controls_b[CONTROL_INDEX_TOUCH_CURSOR_RIGHT]'] = str(JOY_AXIS_POSITIVE + x_axis.code)
        controls['controls_b[CONTROL_INDEX_TOUCH_CURSOR_UP]'] = str(JOY_AXIS_NEGATIVE + y_axis.code)
        controls['controls_b[CONTROL_INDEX_TOUCH_CURSOR_DOWN]'] = str(JOY_AXIS_POSITIVE + y_axis.code)
    return controls

def _sync_drastic_home(bin_path: Path) -> None:
    package_dir = bin_path.parent
    installed = DRASTIC_HOME / 'version'
    shipped = package_dir.parent / 'version'
    if installed.is_file() and shipped.is_file() and installed.read_text() == shipped.read_text():
        return
    shutil.copytree(package_dir, DRASTIC_HOME, dirs_exist_ok=True)
    if shipped.is_file():
        shutil.copy(shipped, installed)

def _read_drastic_cfg() -> dict[str, str]:
    config: dict[str, str] = {}
    if not DRASTIC_CFG.is_file():
        return config
    for line in DRASTIC_CFG.read_text(encoding='ascii', errors='ignore').splitlines():
        key, sep, value = line.partition('=')
        if sep:
            config[key.strip()] = value.strip()
    return config

def _write_drastic_cfg(ctx: LaunchContext, conf: dict[str, str]) -> None:
    config = _read_drastic_cfg()
    config.update({
        'enable_sound': '1',
        'rtc_system_time': '1',
        'frameskip_type': _conf_value(conf, 'drastic_frameskip_type', '0'),
        'frameskip_value': _conf_value(conf, 'drastic_frameskip_value', '1'),
        'hires_3d': _conf_value(conf, 'drastic_hires', '0'),
        'threaded_3d': _conf_value(conf, 'drastic_threaded', '0'),
    })
    config.update(HOTKEY_CONTROLS)
    profile = _pick_es_profile(_load_es_input_configs(), ctx.controllers[0]) if ctx.controllers else None
    config.update(_pad_controls(profile))

    DRASTIC_CFG.parent.mkdir(parents=True, exist_ok=True)
    DRASTIC_CFG.write_text(''.join(f'{key} = {value}\n' for key, value in config.items()), encoding='ascii')

def launch_drastic(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('drastic')
    if bin_path is None:
        _log.error("drastic not found")
        return 1
    _sync_drastic_home(bin_path)
    conf = _load_hippos_conf()
    _write_drastic_cfg(ctx, conf)

    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'drastic', [str(DRASTIC_HOME / 'drastic'), str(ctx.rom)], env, cwd=DRASTIC_HOME)
    return result.returncode
