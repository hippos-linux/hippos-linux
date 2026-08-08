from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from emulatorlauncher_shared import (
    ControllerInfo,
    ESControllerProfile,
    LaunchContext,
    _build_game_env,
    _conf_value,
    _find_emulator_bin_in_package,
    _load_es_input_configs,
    _load_hippos_conf,
    _pick_es_profile,
    _run_game_command,
    _write_unix_settings_file,
)

from HipposPaths import CONFIGS, SAVES, USERDATA


def _openbor_guess_core(rom: Path) -> str:
    match = re.search(r'\[.*([0-9]{4})\]+', rom.name)
    if match is None:
        return 'openbor7530'
    version = int(match.group(1))
    if version < 6000:
        return 'openbor4432'
    if version < 6500:
        return 'openbor6412'
    if version < 7530:
        return 'openbor7142'
    return 'openbor7530'


def _openbor_binding_value(
    profile: Optional[ESControllerProfile],
    ctrl: ControllerInfo,
    logical_name: str,
    joy_max_inputs: int,
    new_axis_vals: bool,
    invert_axis: bool = False,
) -> int:
    if profile is None:
        return 0

    binding = profile.inputs.get(logical_name)
    if binding is None:
        return 0

    value = 0
    if binding.type == 'button':
        value = 1 + ctrl.index * joy_max_inputs + int(binding.code)
    elif binding.type == 'hat':
        if new_axis_vals:
            hatfirst = 1 + ctrl.index * joy_max_inputs + int(ctrl.nb_buttons) + 4 * int(binding.code)
            if binding.value == 2:
                hatfirst += 3
            elif binding.value == 4:
                hatfirst += 1
            elif binding.value == 8:
                hatfirst += 2
        else:
            hatfirst = 1 + ctrl.index * joy_max_inputs + int(ctrl.nb_buttons) + 2 * int(ctrl.nb_axes) + 4 * int(binding.code)
            if binding.value == 2:
                hatfirst += 1
            elif binding.value == 4:
                hatfirst += 2
            elif binding.value == 8:
                hatfirst += 3
        value = hatfirst
    elif binding.type == 'axis':
        axisfirst = 1 + ctrl.index * joy_max_inputs + int(ctrl.nb_buttons) + 2 * int(binding.code)
        if new_axis_vals:
            axisfirst += int(ctrl.nb_hats) * 4
        if ((invert_axis and int(binding.value) < 0) or (not invert_axis and int(binding.value) > 0)):
            axisfirst += 1
        value = axisfirst

    if binding.type != 'keyboard':
        value += 600
    return value


def _write_openbor_config(ctx: LaunchContext) -> str:
    conf = _load_hippos_conf()
    profiles = _load_es_input_configs()
    OPENBOR_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    OPENBOR_SAVE_DIR.mkdir(parents=True, exist_ok=True)
    OPENBOR_ROM_DIR.mkdir(parents=True, exist_ok=True)

    core = ctx.core if ctx.core in OPENBOR_CONFIG_FILES else _openbor_guess_core(ctx.rom)
    config_path = OPENBOR_CONFIG_DIR / OPENBOR_CONFIG_FILES.get(core, 'config7530.ini')

    items: list[tuple[str, object]] = [
        ('fullscreen', '1'),
        ('usegl', '1'),
        ('usejoy', '1'),
        ('stretch', _conf_value(conf, 'openbor_ratio', '0')),
        ('swfilter', _conf_value(conf, 'openbor_filter', '0')),
        ('vsync', _conf_value(conf, 'openbor_vsync', '1')),
        ('fpslimit', _conf_value(conf, 'openbor_limit', '0')),
    ]

    joy_max_inputs = 32 if core == 'openbor4432' else 64
    new_axis_vals = core == 'openbor7142'
    for idx, ctrl in enumerate(ctx.controllers[:5]):
        profile = _pick_es_profile(profiles, ctrl)
        items.extend([
            (f'keys.{idx}.0', _openbor_binding_value(profile, ctrl, 'up', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.1', _openbor_binding_value(profile, ctrl, 'down', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.2', _openbor_binding_value(profile, ctrl, 'left', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.3', _openbor_binding_value(profile, ctrl, 'right', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.4', _openbor_binding_value(profile, ctrl, 'b', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.5', _openbor_binding_value(profile, ctrl, 'x', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.6', _openbor_binding_value(profile, ctrl, 'pageup', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.7', _openbor_binding_value(profile, ctrl, 'pagedown', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.8', _openbor_binding_value(profile, ctrl, 'a', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.9', _openbor_binding_value(profile, ctrl, 'y', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.10', _openbor_binding_value(profile, ctrl, 'start', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.11', _openbor_binding_value(profile, ctrl, 'l2', joy_max_inputs, new_axis_vals)),
        ])
        if idx == 0:
            items.append((f'keys.{idx}.12', _openbor_binding_value(profile, ctrl, 'hotkey', joy_max_inputs, new_axis_vals)))
        else:
            items.append((f'keys.{idx}.12', '0'))
        items.extend([
            (f'keys.{idx}.13', _openbor_binding_value(profile, ctrl, 'joystick1up', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.14', _openbor_binding_value(profile, ctrl, 'joystick1up', joy_max_inputs, new_axis_vals, True)),
            (f'keys.{idx}.15', _openbor_binding_value(profile, ctrl, 'joystick1left', joy_max_inputs, new_axis_vals)),
            (f'keys.{idx}.16', _openbor_binding_value(profile, ctrl, 'joystick1left', joy_max_inputs, new_axis_vals, True)),
            (f'joyrumble.{idx}', _conf_value(conf, 'openbor_rumble', '0')),
        ])

    _write_unix_settings_file(config_path, items)
    return core


def launch_openbor(ctx: LaunchContext) -> int:
    core = _write_openbor_config(ctx)
    binary_name = OPENBOR_BINARIES.get(core, 'OpenBOR7530')
    bin_path = _find_emulator_bin_in_package('openbor', binary_name, 'OpenBOR')
    if bin_path is None:
        return 1

    cmd = [str(bin_path), str(ctx.rom)]
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'openbor', cmd, env, cwd=OPENBOR_ROM_DIR)
    return result.returncode


OPENBOR_CONFIG_DIR = CONFIGS / 'openbor'
OPENBOR_SAVE_DIR = SAVES / 'openbor'
OPENBOR_ROM_DIR = USERDATA / 'roms' / 'openbor'
OPENBOR_CONFIG_FILES = {
    'openbor4432': 'config4432.ini',
    'openbor6412': 'config6412.ini',
    'openbor7142': 'config7142.ini',
    'openbor7530': 'config7530.ini',
}
OPENBOR_BINARIES = {
    'openbor4432': 'OpenBOR4432',
    'openbor6412': 'OpenBOR6412',
    'openbor7142': 'OpenBOR7142',
    'openbor7530': 'OpenBOR7530',
}
