from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_value,
    _find_emulator_bin,
    _load_effective_hippos_conf,
    _load_es_input_configs,
    _pick_es_profile,
    _run_game_command,
    configure_emulator,
)

from HipposPaths import CACHE, CONFIGS, SAVES


def _play_device_id(profile: Optional[object], ctrl: object) -> str:
    if profile is not None and getattr(profile, 'device_guid', None):
        return profile.device_guid
    if getattr(ctrl, 'guid', None):
        return ctrl.guid
    if getattr(ctrl, 'device_path', None):
        return ctrl.device_path
    return f'player{ctrl.player}'


def write_play_config(ctx: LaunchContext) -> None:
    conf = _load_effective_hippos_conf()
    profiles = _load_es_input_configs()
    PLAY_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PLAY_INPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAY_SAVES_DIR.mkdir(parents=True, exist_ok=True)

    root = ET.Element('Config')
    if PLAY_CONFIG_FILE.exists():
        try:
            root = ET.parse(PLAY_CONFIG_FILE).getroot()
        except ET.ParseError:
            pass

    preferences = {
        'ps2.arcaderoms.directory': {'Type': 'path', 'Value': '/userdata/roms/namco2x6'},
        'ui.showexitconfirmation': {'Type': 'boolean', 'Value': 'false'},
        'ui.pausewhenfocuslost': {'Type': 'boolean', 'Value': 'false'},
        'ui.showeecpuusage': {'Type': 'boolean', 'Value': 'false'},
        'ps2.limitframerate': {'Type': 'boolean', 'Value': 'true'},
        'renderer.widescreen': {'Type': 'boolean', 'Value': 'false'},
        'system.language': {'Type': 'integer', 'Value': '1'},
        'video.gshandler': {'Type': 'integer', 'Value': '0'},
        'renderer.opengl.resfactor': {'Type': 'integer', 'Value': '1'},
        'renderer.presentationmode': {'Type': 'integer', 'Value': '1'},
        'renderer.opengl.forcebilineartextures': {'Type': 'boolean', 'Value': 'false'},
    }

    for pref_name, pref_attrs in preferences.items():
        pref_element = root.find(f".//Preference[@Name='{pref_name}']")
        if pref_element is None:
            pref_element = ET.SubElement(root, 'Preference', Name=pref_name)
        for attr_name, attr_value in pref_attrs.items():
            pref_element.attrib[attr_name] = attr_value

        if pref_name == 'ps2.limitframerate' and (vsync := _conf_value(conf, 'play_vsync', '')):
            pref_element.attrib['Value'] = vsync
        if pref_name == 'renderer.widescreen' and (widescreen := _conf_value(conf, 'play_widescreen', '')):
            pref_element.attrib['Value'] = widescreen
        if pref_name == 'system.language' and (language := _conf_value(conf, 'play_language', '')):
            pref_element.attrib['Value'] = language
        if pref_name == 'video.gshandler' and (api := _conf_value(conf, 'play_api', '')):
            pref_element.attrib['Value'] = api
        if pref_name == 'renderer.opengl.resfactor' and (scale := _conf_value(conf, 'play_scale', '')):
            pref_element.attrib['Value'] = scale
        if pref_name == 'renderer.presentationmode' and (mode := _conf_value(conf, 'play_mode', '')):
            pref_element.attrib['Value'] = mode
        if pref_name == 'renderer.opengl.forcebilineartextures' and (filter_value := _conf_value(conf, 'play_filter', '')):
            pref_element.attrib['Value'] = filter_value

    input_config = ET.Element('Config')
    play_mapping = {
        'a': 'circle',
        'b': 'cross',
        'x': 'triangle',
        'y': 'square',
        'start': 'start',
        'select': 'select',
        'pageup': 'l1',
        'pagedown': 'r1',
        'joystick1left': 'analog_left_x',
        'joystick1up': 'analog_left_y',
        'joystick2left': 'analog_right_x',
        'joystick2up': 'analog_right_y',
        'up': 'dpad_up',
        'down': 'dpad_down',
        'left': 'dpad_left',
        'right': 'dpad_right',
        'l2': 'l2',
        'r2': 'r2',
        'l3': 'l3',
        'r3': 'r3',
    }

    for nplayer, controller in enumerate(ctx.controllers[:2], start=1):
        profile = _pick_es_profile(profiles, controller)
        if profile is None:
            continue
        pad_guid = _play_device_id(profile, controller)
        provider_id = 1702257782

        ET.SubElement(
            input_config,
            'Preference',
            Name=f'input.pad{nplayer}.analog.sensitivity',
            Type='float',
            Value='1.000000',
        )

        for input_binding in profile.inputs.values():
            if input_binding.name not in play_mapping:
                continue
            if ctx.lightgun and play_mapping[input_binding.name] in {'circle', 'triangle', 'start', 'select'}:
                continue

            if input_binding.type == 'axis':
                key_type = 1
                binding_type = 1
                key_id = input_binding.code
                hat_value = -1
            elif input_binding.type == 'hat':
                key_type = 2
                binding_type = 3
                key_id = 17 if input_binding.name in ['up', 'down'] else 16
                hat_value = 4 if input_binding.name in ['up', 'left'] else 0
            elif input_binding.type == 'button':
                key_type = 0
                binding_type = input_binding.value
                key_id = input_binding.code
                hat_value = -1
            else:
                continue

            target_name = play_mapping[input_binding.name]
            ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{target_name}.bindingtarget1.deviceId', Type='string', Value=pad_guid)
            ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{target_name}.bindingtarget1.keyId', Type='integer', Value=str(key_id))
            ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{target_name}.bindingtarget1.keyType', Type='integer', Value=str(key_type))
            ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{target_name}.bindingtarget1.providerId', Type='integer', Value=str(provider_id))
            ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{target_name}.bindingtype', Type='integer', Value=str(binding_type))
            ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{target_name}.povhatbinding.refvalue', Type='integer', Value=str(hat_value))

    if ctx.lightgun and ctx.controllers:
        gun_count = max(1, min(len(ctx.controllers) + 1, 3))
        for nplayer in range(1, gun_count + 1):
            for key_id, ps2_btn in [
                (272, 'circle'),
                (273, 'triangle'),
                (274, 'start'),
                (257, 'select'),
            ]:
                ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{ps2_btn}.bindingtarget1.deviceId', Type='string', Value='0:0:0:0:0:0')
                ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{ps2_btn}.bindingtarget1.keyId', Type='integer', Value=str(key_id))
                ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{ps2_btn}.bindingtarget1.keyType', Type='integer', Value='0')
                ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{ps2_btn}.bindingtarget1.providerId', Type='integer', Value='1702257782')
                ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{ps2_btn}.bindingtype', Type='integer', Value='1')
                ET.SubElement(input_config, 'Preference', Name=f'input.pad{nplayer}.{ps2_btn}.povhatbinding.refvalue', Type='integer', Value='-1')

    ET.ElementTree(root).write(PLAY_CONFIG_FILE, encoding='utf-8')
    ET.ElementTree(input_config).write(PLAY_INPUT_FILE, encoding='utf-8')


def launch_play(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('play')
    if bin_path is None:
        return 1

    write_play_config(ctx)
    conf = _load_effective_hippos_conf()
    cmd: list[str | Path] = [str(bin_path), '--fullscreen']
    if not configure_emulator(ctx.rom):
        if ctx.rom.suffix.lower() == '.zip':
            cmd += ['--arcade', ctx.rom.stem]
        else:
            cmd += ['--disc', ctx.rom]

    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(PLAY_CONFIG_DIR)
    env['XDG_DATA_HOME'] = str(PLAY_CONFIG_DIR)
    env['XDG_CACHE_HOME'] = str(CACHE)
    env['QT_QPA_PLATFORM'] = 'xcb'
    result = _run_game_command(ctx, 'play', cmd, env)
    return result.returncode


PLAY_CONFIG_DIR = CONFIGS / 'play'
PLAY_DATA_DIR = PLAY_CONFIG_DIR / 'Play Data Files'
PLAY_CONFIG_FILE = PLAY_DATA_DIR / 'config.xml'
PLAY_INPUT_FILE = PLAY_DATA_DIR / 'inputprofiles' / 'default.xml'
PLAY_SAVES_DIR = SAVES / 'ps2'
