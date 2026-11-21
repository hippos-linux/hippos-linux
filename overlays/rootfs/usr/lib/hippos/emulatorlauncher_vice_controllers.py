from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from evdev import InputDevice, ecodes

from emulatorlauncher_shared import LaunchContext
from HipposPaths import CONFIGS

_VICE_MACHINE_NAMES: dict[str, str] = {
    'x64':     'C64SC',
    'x64sc':   'C64SC',
    'x64dtv':  'C64DTV',
    'xscpu64': 'SCPU64',
    'x128':    'C128',
    'xvic':    'VIC20',
    'xplus4':  'PLUS4',
    'xpet':    'PET',
    'xcbm2':   'CBM-II',
    'xcbm5x0': 'CBM-II-5x0',
}

_VICE_PLAYER_PORTS: dict[str, tuple[int, ...]] = {
    'x64':     (2, 1),
    'x64sc':   (2, 1),
    'x64dtv':  (2, 1),
    'xscpu64': (2, 1),
    'x128':    (2, 1),
    'xcbm5x0': (2, 1),
    'xplus4':  (1, 2),
    'xvic':    (1,),
}

_VICE_JOYDEV_FIRST_HOST = 4

_VICE_INPUT_AXIS, _VICE_INPUT_BUTTON = 0, 1
_VICE_ACTION_JOYSTICK, _VICE_ACTION_UI_ACTIVATE = 1, 4
_VICE_PIN_UP, _VICE_PIN_DOWN, _VICE_PIN_LEFT, _VICE_PIN_RIGHT = 1, 2, 4, 8
_VICE_PIN_FIRE1, _VICE_PIN_FIRE2, _VICE_PIN_FIRE3 = 16, 32, 64

_VICE_BUTTON_ACTIONS: tuple[tuple[int, int, int], ...] = (
    (ecodes.BTN_SOUTH,      _VICE_ACTION_JOYSTICK,    _VICE_PIN_FIRE1),
    (ecodes.BTN_EAST,       _VICE_ACTION_JOYSTICK,    _VICE_PIN_FIRE2),
    (ecodes.BTN_WEST,       _VICE_ACTION_JOYSTICK,    _VICE_PIN_FIRE3),
    (ecodes.BTN_DPAD_UP,    _VICE_ACTION_JOYSTICK,    _VICE_PIN_UP),
    (ecodes.BTN_DPAD_DOWN,  _VICE_ACTION_JOYSTICK,    _VICE_PIN_DOWN),
    (ecodes.BTN_DPAD_LEFT,  _VICE_ACTION_JOYSTICK,    _VICE_PIN_LEFT),
    (ecodes.BTN_DPAD_RIGHT, _VICE_ACTION_JOYSTICK,    _VICE_PIN_RIGHT),
    (ecodes.BTN_SELECT,     _VICE_ACTION_UI_ACTIVATE, 0),
)

_VICE_AXIS_ACTIONS: tuple[tuple[int, int, int], ...] = (
    (ecodes.ABS_HAT0X, _VICE_PIN_LEFT, _VICE_PIN_RIGHT),
    (ecodes.ABS_HAT0Y, _VICE_PIN_UP,   _VICE_PIN_DOWN),
    (ecodes.ABS_X,     _VICE_PIN_LEFT, _VICE_PIN_RIGHT),
    (ecodes.ABS_Y,     _VICE_PIN_UP,   _VICE_PIN_DOWN),
)

_VICE_GAMEPAD_BUTTONS = frozenset({
    ecodes.BTN_SOUTH, ecodes.BTN_EAST, ecodes.BTN_NORTH, ecodes.BTN_WEST,
    ecodes.BTN_START, ecodes.BTN_SELECT, ecodes.BTN_TL, ecodes.BTN_TR,
    ecodes.BTN_JOYSTICK,
})
_VICE_GAMEPAD_AXES = frozenset({
    ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_RX, ecodes.ABS_RY,
    ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y,
})

@dataclass(frozen=True)
class _ViceJoystick:
    path: str
    buttons: tuple[int, ...]
    axes: tuple[int, ...]

def _vice_joysticks() -> list[_ViceJoystick]:
    joysticks = []
    for node in sorted(Path('/dev/input').glob('event*')):
        try:
            device = InputDevice(str(node))
        except OSError:
            continue
        caps = device.capabilities()
        device.close()
        keys = set(caps.get(ecodes.EV_KEY, ()))
        axes = {code for code, _info in caps.get(ecodes.EV_ABS, ())}
        if keys & _VICE_GAMEPAD_BUTTONS and axes & _VICE_GAMEPAD_AXES:
            joysticks.append(_ViceJoystick(
                path=str(node),
                buttons=tuple(sorted(c for c in keys if c >= ecodes.BTN_JOYSTICK)),
                axes=tuple(sorted(c for c in axes if c < ecodes.ABS_RESERVED)),
            ))
    return joysticks

def _vice_joymap_lines(device: int, joystick: _ViceJoystick) -> list[str]:
    lines = []
    for code, action, pin in _VICE_BUTTON_ACTIONS:
        if code in joystick.buttons:
            entry = f'{device} {_VICE_INPUT_BUTTON} {joystick.buttons.index(code)} {action}'
            lines.append(f'{entry} {pin}' if action == _VICE_ACTION_JOYSTICK else entry)
    for code, negative_pin, positive_pin in _VICE_AXIS_ACTIONS:
        if code in joystick.axes:
            row = 2 * joystick.axes.index(code)
            lines.append(f'{device} {_VICE_INPUT_AXIS} {row} {_VICE_ACTION_JOYSTICK} {positive_pin}')
            lines.append(f'{device} {_VICE_INPUT_AXIS} {row + 1} {_VICE_ACTION_JOYSTICK} {negative_pin}')
    return lines

def configure_vice_joysticks(ctx: LaunchContext, binary: str) -> list[str]:
    joysticks = _vice_joysticks()
    device_by_path = {joystick.path: index for index, joystick in enumerate(joysticks)}
    ports = _VICE_PLAYER_PORTS.get(binary, ())

    lines = ['!CLEAR']
    args: list[str] = []
    for ctrl, port in zip(sorted(ctx.controllers, key=lambda c: c.player), ports):
        device = device_by_path.get(os.path.realpath(ctrl.device_path)) if ctrl.device_path else None
        if device is None:
            continue
        lines += ['', f'# Player {ctrl.player}: {ctrl.name}', *_vice_joymap_lines(device, joysticks[device])]
        args += [f'-joydev{port}', str(_VICE_JOYDEV_FIRST_HOST + device)]

    joymap = CONFIGS / 'vice' / f'gtk3-joymap-{_VICE_MACHINE_NAMES[binary]}.vjm'
    joymap.parent.mkdir(parents=True, exist_ok=True)
    joymap.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return args
