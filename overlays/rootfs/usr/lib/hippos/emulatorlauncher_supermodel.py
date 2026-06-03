from __future__ import annotations

from emulatorlauncher_impl import (
    LaunchContext,
    SAVES,
    SUPERMODEL_CONFIG_DIR,
    SUPERMODEL_INI,
    SUPERMODEL_TEMPLATE,
    _build_game_env,
    _conf_bool,
    _display_resolution_from_conf,
    _find_emulator_bin,
    _load_effective_hippos_conf,
    _new_ini_parser,
    _run_game_command,
)


def write_supermodel_config(ctx: LaunchContext) -> None:
    conf = _load_effective_hippos_conf()
    SUPERMODEL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    target = _new_ini_parser()
    if SUPERMODEL_TEMPLATE.exists():
        target.read(SUPERMODEL_TEMPLATE, encoding='utf-8')
    else:
        if not target.has_section('Global'):
            target.add_section('Global')
        if not target.has_section(ctx.rom.stem):
            target.add_section(ctx.rom.stem)

    for section in ('Global', ctx.rom.stem):
        if not target.has_section(section):
            target.add_section(section)
        if section != 'Global':
            target.set(section, 'InputSystem', 'to be defined')
        for key in list(target[section].keys()):
            if key == 'InputSystem':
                target.set(section, key, 'evdev' if ctx.lightgun else 'sdlgamepad')
            elif ctx.lightgun:
                if key == 'InputAnalogJoyX':
                    target.set(section, key, 'MOUSE1_XAXIS_INV')
                elif key == 'InputAnalogJoyY':
                    target.set(section, key, 'MOUSE1_YAXIS_INV')
                elif key in ('InputGunX', 'InputAnalogGunX'):
                    target.set(section, key, 'MOUSE1_XAXIS')
                elif key in ('InputGunY', 'InputAnalogGunY'):
                    target.set(section, key, 'MOUSE1_YAXIS')
                elif key in ('InputTrigger', 'InputAnalogTriggerLeft', 'InputAnalogJoyTrigger'):
                    target.set(section, key, 'MOUSE1_LEFT_BUTTON')
                elif key in ('InputOffscreen', 'InputAnalogTriggerRight'):
                    target.set(section, key, 'MOUSE1_RIGHT_BUTTON')
                elif key == 'InputStart1':
                    target.set(section, key, 'MOUSE1_BUTTONX1,JOY1_BUTTON8')
                elif key == 'InputCoin1':
                    target.set(section, key, 'MOUSE1_BUTTONX2,JOY1_BUTTON7')
                elif key == 'InputAnalogJoyEvent':
                    target.set(section, key, 'KEY_S,MOUSE1_MIDDLE_BUTTON')
                elif key == 'InputAnalogJoyX2':
                    target.set(section, key, 'MOUSE2_XAXIS_INV')
                elif key == 'InputAnalogJoyY2':
                    target.set(section, key, 'MOUSE2_YAXIS_INV')
                elif key in ('InputGunX2', 'InputAnalogGunX2'):
                    target.set(section, key, 'MOUSE2_XAXIS')
                elif key in ('InputGunY2', 'InputAnalogGunY2'):
                    target.set(section, key, 'MOUSE2_YAXIS')
                elif key in ('InputTrigger2', 'InputAnalogTriggerLeft2', 'InputAnalogJoyTrigger2'):
                    target.set(section, key, 'MOUSE2_LEFT_BUTTON')
                elif key in ('InputOffscreen2', 'InputAnalogTriggerRight2'):
                    target.set(section, key, 'MOUSE2_RIGHT_BUTTON')
                elif key == 'InputStart2':
                    target.set(section, key, 'MOUSE2_BUTTONX1,JOY2_BUTTON8')
                elif key == 'InputCoin2':
                    target.set(section, key, 'MOUSE2_BUTTONX2,JOY2_BUTTON7')
                elif key == 'InputAnalogJoyEvent2':
                    target.set(section, key, 'MOUSE2_MIDDLE_BUTTON')

    with SUPERMODEL_INI.open('w', encoding='utf-8') as fh:
        target.write(fh)


def launch_supermodel(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('supermodel')
    if bin_path is None:
        return 1

    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    write_supermodel_config(ctx)

    conf = _load_effective_hippos_conf()
    cmd: list[str] = [str(bin_path), '-fullscreen', '-channels=2']
    if ctx.lightgun:
        gun_count = max(1, min(2, len(ctx.controllers) or 1))
        cmd.append(f'-crosshairs={1 if gun_count == 1 else 3}')
    display_resolution = _display_resolution_from_conf(conf)
    if display_resolution is not None:
        width, height = display_resolution
        cmd.append(f'-res={width},{height}')
    cmd.extend(['-log-output=/userdata/system/logs/Supermodel.log', str(ctx.rom)])

    env = _build_game_env(conf, ctx)
    env['SDL_VIDEODRIVER'] = 'x11'
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    result = _run_game_command(ctx, 'supermodel', cmd, env)
    return result.returncode
