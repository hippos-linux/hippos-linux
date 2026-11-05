from __future__ import annotations

import shutil
from pathlib import Path

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _display_resolution_from_conf,
    _find_emulator_bin,
    _load_effective_hippos_conf,
    _new_ini_parser,
    _run_game_command,
)

from HipposPaths import CONFIGS


def _prepare_run_dir(variant: str, share: Path) -> Path:
    """Supermodel uses ./Config, ./NVRAM, ./Saves and ./Assets when a Config
    folder exists in its working directory (every version checks there first),
    so each variant gets its own run folder. Games.xml follows the artifact."""
    run_dir = CONFIGS / variant
    config_dir = run_dir / 'Config'
    config_dir.mkdir(parents=True, exist_ok=True)
    for name in ('Games.xml', 'Music.xml'):
        src = share / 'Config' / name
        if src.is_file():
            shutil.copyfile(src, config_dir / name)
    assets = run_dir / 'Assets'
    if (share / 'Assets').is_dir() and not assets.exists():
        assets.symlink_to(share / 'Assets')
    return run_dir


def write_supermodel_config(ctx: LaunchContext, run_dir: Path, share: Path) -> None:
    target = _new_ini_parser()
    template = share / 'Config' / 'Supermodel.ini'
    if template.exists():
        # Supermodel writes sections as "[ Global ]"; configparser keeps the spaces.
        raw = _new_ini_parser()
        raw.read(template, encoding='utf-8')
        for section in raw.sections():
            name = section.strip()
            if not target.has_section(name):
                target.add_section(name)
            for key, value in raw.items(section):
                target.set(name, key, value)
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

    with (run_dir / 'Config' / 'Supermodel.ini').open('w', encoding='utf-8') as fh:
        target.write(fh)


# Builds of the same emulator: upstream, a fork, and the 0.3a line.
SUPERMODEL_VARIANTS = ('supermodel', 'supermodel-es', 'supermodel-legacy')


def launch_supermodel(ctx: LaunchContext) -> int:
    variant = ctx.emulator if ctx.emulator in SUPERMODEL_VARIANTS else 'supermodel'
    bin_path = _find_emulator_bin(variant)
    if bin_path is None:
        return 1

    share = bin_path.parent.parent / 'share'
    run_dir = _prepare_run_dir(variant, share)
    write_supermodel_config(ctx, run_dir, share)

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
    result = _run_game_command(ctx, variant, cmd, env, cwd=run_dir)
    return result.returncode

