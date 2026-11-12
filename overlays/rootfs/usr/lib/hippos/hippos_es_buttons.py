from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from evdev import ecodes

from hippos_padtokey import sdl_button_codes

ES_INPUT_FILES = (
    Path('/userdata/system/configs/emulationstation/es_input.cfg'),
    Path('/usr/share/emulationstation/es_input.cfg'),
)

FALLBACK_GAMEPAD_BUTTONS = {
    ecodes.BTN_MODE:   'hotkey',
    ecodes.BTN_START:  'start',
    ecodes.BTN_SELECT: 'select',
    ecodes.BTN_EAST:   'a',
    ecodes.BTN_SOUTH:  'b',
    ecodes.BTN_WEST:   'x',
    ecodes.BTN_NORTH:  'y',
    ecodes.BTN_TL:     'pageup',
    ecodes.BTN_TR:     'pagedown',
    ecodes.BTN_TL2:    'l2',
    ecodes.BTN_TR2:    'r2',
    ecodes.BTN_THUMBL: 'l3',
    ecodes.BTN_THUMBR: 'r3',
}

DPAD_BUTTONS = {
    ecodes.BTN_DPAD_UP: 'up', ecodes.BTN_DPAD_DOWN: 'down',
    ecodes.BTN_DPAD_LEFT: 'left', ecodes.BTN_DPAD_RIGHT: 'right',
}


def es_input_root() -> ET.Element | None:
    path = next((path for path in ES_INPUT_FILES if path.exists()), None)
    if path is None:
        return None
    try:
        return ET.parse(path).getroot()
    except ET.ParseError:
        return None


def joystick_button_maps(root: ET.Element | None) -> dict[str, dict[int, str]]:
    maps: dict[str, dict[int, str]] = {}
    if root is None:
        return maps
    for config in root.findall('inputConfig'):
        if config.get('type') != 'joystick':
            continue
        by_index: dict[int, str] = {}
        for node in config.findall('input'):
            name, index = node.get('name'), node.get('id') or node.get('code')
            if node.get('type') != 'button' or not name or index is None:
                continue
            try:
                by_index[int(index)] = name
            except ValueError:
                continue
        if config.get('deviceName') and by_index:
            maps[config.get('deviceName')] = by_index
    return maps


def button_names(device_name: str, keys: set[int], maps: dict[str, dict[int, str]]) -> dict[int, str]:
    names = {code: name for code, name in FALLBACK_GAMEPAD_BUTTONS.items() if code in keys}
    codes = sdl_button_codes(keys)
    for index, name in maps.get(device_name, {}).items():
        if index < len(codes):
            names[codes[index]] = name
    return names
