from __future__ import annotations

import json
import logging
import os
import subprocess
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import evdev
    from emulatorlauncher_shared import ControllerInfo, ESBinding, ESControllerProfile

_log = logging.getLogger(__name__)

USER_MAPS   = Path('/userdata/system/configs/evmapy')
SYSTEM_MAPS = Path('/usr/share/evmapy')
MAPS_FILE   = Path('/run/hippos/padtokey.json')
LAUNCH_FILE = Path('/run/hippos/padtokey-launch.json')
POINTER_MAP = SYSTEM_MAPS / 'controller-as-mouse.keys'
HOTKEYS_BIN = Path('/usr/lib/hippos/hippos-hotkeys')

DEFAULT_MOUSE_LEVEL = 5
MOUSE_SPEED_AT_DEFAULT_LEVEL = 8.0
MOUSE_INTERVAL = 0.006
MOUSE_DEADZONE = 0.05
SCROLL_NOTCHES_PER_SECOND = 20.0
DIRECTION_THRESHOLD = 0.5

HAT_DIRECTIONS = {1: ('y', -1), 2: ('x', 1), 4: ('y', 1), 8: ('x', -1)}
OPPOSITE_DIRECTIONS = {'down': 'up', 'right': 'left'}


def default_keys_files(system: str, emulator: str) -> list[Path]:
    candidates = [
        USER_MAPS / f'{system}.{emulator}.keys',
        USER_MAPS / f'{system}.keys',
        USER_MAPS / f'{emulator}.keys',
        USER_MAPS / 'any.keys',
        SYSTEM_MAPS / f'{system}.{emulator}.keys',
        SYSTEM_MAPS / f'{system}.keys',
        SYSTEM_MAPS / f'{emulator}.keys',
        SYSTEM_MAPS / 'any.keys',
    ]
    return [p for p in dict.fromkeys(candidates) if p.exists()]


def game_keys_file(rom: Path) -> Path:
    return rom / 'padto.keys' if rom.is_dir() else rom.parent / f'{rom.name}.keys'


def find_keys_files(system: str, emulator: str, rom: Path, default_maps: bool, pointer: bool = False) -> list[Path]:
    game_map = game_keys_file(rom)
    files = [game_map] if game_map.exists() else []
    defaults = default_keys_files(system, emulator) if default_maps else []
    if pointer and not defaults:
        defaults = [POINTER_MAP]
    return files + defaults


def merge_keys_files(files: list[Path]) -> dict[str, list[dict]]:
    merged: dict[str, dict[str, dict]] = defaultdict(dict)
    for path in files:
        try:
            data: dict = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("padtokey: could not parse %s: %s", path, exc)
            continue
        for player_key, actions in data.items():
            for action in actions:
                trigger = action.get('trigger', '')
                key = '+'.join(sorted(trigger)) if isinstance(trigger, list) else trigger
                if key and key not in merged[player_key]:
                    merged[player_key][key] = action
    return {player_key: list(actions.values()) for player_key, actions in merged.items()}


def _binding_input(binding: ESBinding, invert: bool = False) -> dict[str, Any] | None:
    if binding.type == 'button':
        return {'type': 'button', 'id': binding.code}
    if binding.type == 'hat':
        return {'type': 'hat', 'id': binding.code, 'value': binding.value}
    if binding.type == 'axis':
        direction = 1 if binding.value > 0 else -1
        return {'type': 'axis', 'id': binding.code, 'value': -direction if invert else direction}
    return None


def _trigger_input(name: str, profile: ESControllerProfile) -> dict[str, Any] | None:
    if name in profile.inputs:
        return _binding_input(profile.inputs[name])
    for direction, opposite in OPPOSITE_DIRECTIONS.items():
        if name.endswith(direction) and name.startswith('joystick'):
            binding = profile.inputs.get(name[:-len(direction)] + opposite)
            if binding is not None and binding.type == 'axis':
                return _binding_input(binding, invert=True)
    return None


def resolve_actions(actions: list[dict], profile: ESControllerProfile) -> list[dict[str, Any]]:
    resolved = []
    for action in actions:
        trigger = action.get('trigger', '')
        if action.get('type') in ('mouse', 'scroll'):
            x = profile.inputs.get(f'{trigger}left')
            y = profile.inputs.get(f'{trigger}up')
            if x is None or y is None or x.type != 'axis' or y.type != 'axis':
                _log.info("padtokey: %s has no stick for %r", profile.device_name, trigger)
                continue
            resolved.append({action['type']: [x.code, y.code]})
            continue
        targets = action.get('target')
        targets = targets if isinstance(targets, list) else [targets]
        parts = trigger if isinstance(trigger, list) else trigger.split('+')
        inputs = [_trigger_input(part, profile) for part in parts]
        if not targets or None in targets or None in inputs:
            _log.info("padtokey: %s can't map %r", profile.device_name, trigger)
            continue
        resolved.append({'inputs': inputs, 'keys': targets})
    return resolved


def write_maps(system: str, emulator: str, rom: Path,
               controllers: list[ControllerInfo], profiles: list[ESControllerProfile],
               pointer: bool | None = None) -> bool:
    from emulatorlauncher_shared import _game_or_system_setting, _game_setting, _load_hippos_conf, _pick_es_profile

    conf = _load_hippos_conf()
    default_maps = _game_or_system_setting(conf, system, rom, 'padtokey') != '0' if pointer is None else pointer
    merged = merge_keys_files(find_keys_files(system, emulator, rom, default_maps, pointer=bool(pointer)))
    devices = {}
    for ctrl in controllers:
        actions = merged.get(f'actions_player{ctrl.player}')
        profile = _pick_es_profile(profiles, ctrl)
        if actions and profile is not None and ctrl.device_path:
            devices[ctrl.device_path] = resolve_actions(actions, profile)
    if not devices:
        clear_maps()
        return False
    level = float(_game_setting(conf, system, rom, 'padtokey_mouse_speed') or DEFAULT_MOUSE_LEVEL)
    data = {'mouse_speed': MOUSE_SPEED_AT_DEFAULT_LEVEL * level / DEFAULT_MOUSE_LEVEL, 'devices': devices,
            'pointer': default_maps and bool(pointer or default_keys_files(system, emulator))}
    temporary = MAPS_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps(data))
    os.replace(temporary, MAPS_FILE)
    _log.info("padtokey: maps for %s", ', '.join(devices))
    return True


def clear_maps() -> None:
    MAPS_FILE.unlink(missing_ok=True)


def reload_daemon() -> None:
    subprocess.run([str(HOTKEYS_BIN), '--reload'], capture_output=True)


@contextmanager
def padtokey_context(system: str, emulator: str, rom: Path,
                     controllers: list[ControllerInfo], profiles: list[ESControllerProfile]):
    LAUNCH_FILE.write_text(json.dumps({'system': system, 'emulator': emulator, 'rom': str(rom),
                                       'controllers': [asdict(controller) for controller in controllers]}))
    if write_maps(system, emulator, rom, controllers, profiles):
        reload_daemon()
    try:
        yield
    finally:
        LAUNCH_FILE.unlink(missing_ok=True)
        if MAPS_FILE.exists():
            clear_maps()
            reload_daemon()


def running_game() -> dict[str, Any] | None:
    try:
        return json.loads(LAUNCH_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def pointer_enabled() -> bool:
    return bool(load_maps().get('pointer'))


def set_pointer(enabled: bool) -> bool:
    return reapply_running_game(pointer=enabled)


def reapply_running_game(pointer: bool | None = None) -> bool:
    from emulatorlauncher_shared import ControllerInfo, _load_es_input_configs

    game = running_game()
    if game is None:
        return False
    if pointer is None and pointer_enabled():
        pointer = True
    controllers = [ControllerInfo(**controller) for controller in game['controllers']]
    write_maps(game['system'], game['emulator'], Path(game['rom']), controllers, _load_es_input_configs(),
               pointer=pointer)
    reload_daemon()
    return True


def load_maps() -> dict[str, Any]:
    try:
        return json.loads(MAPS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def sdl_button_codes(keys: set[int]) -> list[int]:
    from evdev import ecodes
    return sorted(c for c in keys if c >= ecodes.BTN_JOYSTICK) + sorted(c for c in keys if c < ecodes.BTN_JOYSTICK)


def sdl_axis_codes(axes: set[int]) -> list[int]:
    from evdev import ecodes
    hats = set(range(ecodes.ABS_HAT0X, ecodes.ABS_HAT3Y + 1))
    return sorted(c for c in axes if c not in hats)


@dataclass
class _Action:
    inputs: frozenset[tuple]
    keys: list[int]


@dataclass
class PadMapper:
    uinput: Any
    actions: list[_Action]
    mouse_axes: tuple[int, int] | None
    scroll_axes: tuple[int, int] | None
    mouse_speed: float
    ranges: dict[int, tuple[int, int]]
    positions: dict[int, float] = field(default_factory=dict)
    scroll_remainder: dict[int, float] = field(default_factory=dict)
    pressed: set[tuple] = field(default_factory=set)
    active: list[_Action] = field(default_factory=list)
    last_move: float = 0.0

    @classmethod
    def build(cls, device: evdev.InputDevice, entries: list[dict], uinput: Any, mouse_speed: float) -> PadMapper:
        from evdev import ecodes
        caps = device.capabilities()
        buttons = sdl_button_codes(set(caps.get(ecodes.EV_KEY, [])))
        abs_info = dict(caps.get(ecodes.EV_ABS, []))
        axes = sdl_axis_codes(set(abs_info))

        def input_key(spec: dict) -> tuple | None:
            index = spec['id']
            if spec['type'] == 'button':
                return ('key', buttons[index]) if index < len(buttons) else None
            if spec['type'] == 'axis':
                return ('abs', axes[index], spec['value']) if index < len(axes) else None
            if spec['type'] == 'hat' and spec['value'] in HAT_DIRECTIONS:
                axis, direction = HAT_DIRECTIONS[spec['value']]
                return ('abs', ecodes.ABS_HAT0X + 2 * index + (axis == 'y'), direction)
            return None

        actions, sticks = [], {}
        for entry in entries:
            stick = next((kind for kind in ('mouse', 'scroll') if kind in entry), None)
            if stick:
                x, y = entry[stick]
                if x < len(axes) and y < len(axes):
                    sticks[stick] = (axes[x], axes[y])
                continue
            inputs = [input_key(spec) for spec in entry['inputs']]
            keys = [ecodes.ecodes[name] for name in entry['keys'] if name in ecodes.ecodes]
            if None not in inputs and keys:
                actions.append(_Action(frozenset(inputs), keys))
        ranges = {code: (info.min, info.max) for code, info in abs_info.items()}
        return cls(uinput, actions, sticks.get('mouse'), sticks.get('scroll'), mouse_speed, ranges)

    def _normalised(self, code: int, value: int) -> float:
        low, high = self.ranges.get(code, (-1, 1))
        centre = (low + high) / 2
        return (value - centre) / ((high - centre) or 1)

    def _press(self, key: tuple) -> None:
        self.pressed.add(key)
        candidates = [a for a in self.actions if key in a.inputs and a.inputs <= self.pressed and a not in self.active]
        if not candidates:
            return
        action = max(candidates, key=lambda a: len(a.inputs))
        if any(action.inputs < other.inputs for other in self.active):
            return
        self.active.append(action)
        self._send(action.keys, 1)

    def _release(self, key: tuple) -> None:
        self.pressed.discard(key)
        for action in [a for a in self.active if key in a.inputs]:
            self.active.remove(action)
            self._send(list(reversed(action.keys)), 0)

    def _send(self, keys: list[int], value: int) -> None:
        from evdev import ecodes
        for code in keys:
            self.uinput.write(ecodes.EV_KEY, code, value)
        self.uinput.syn()

    def handle(self, event: evdev.InputEvent, buttons: bool = True) -> None:
        from evdev import ecodes
        is_button = event.type == ecodes.EV_KEY or (
            event.type == ecodes.EV_ABS and ecodes.ABS_HAT0X <= event.code <= ecodes.ABS_HAT3Y)
        if is_button and not buttons:
            return
        if event.type == ecodes.EV_KEY and event.value in (0, 1):
            (self._press if event.value else self._release)(('key', event.code))
        elif event.type == ecodes.EV_ABS:
            position = self._normalised(event.code, event.value)
            self.positions[event.code] = position
            for direction in (-1, 1):
                key = ('abs', event.code, direction)
                held = position * direction > DIRECTION_THRESHOLD
                if held and key not in self.pressed:
                    self._press(key)
                elif not held and key in self.pressed:
                    self._release(key)

    def _deflected(self, axes: tuple[int, int] | None) -> bool:
        return axes is not None and any(abs(self.positions.get(code, 0.0)) >= MOUSE_DEADZONE for code in axes)

    def mouse_active(self) -> bool:
        return self._deflected(self.mouse_axes) or self._deflected(self.scroll_axes)

    def move_mouse(self, now: float) -> None:
        from evdev import ecodes
        if not self.mouse_active() or now < self.last_move + MOUSE_INTERVAL:
            return
        elapsed = min(now - self.last_move, 10 * MOUSE_INTERVAL)
        self.last_move = now
        if self._deflected(self.mouse_axes):
            for code, rel in zip(self.mouse_axes, (ecodes.REL_X, ecodes.REL_Y)):
                position = self.positions.get(code, 0.0)
                if abs(position) >= MOUSE_DEADZONE:
                    step = int(position * position * self.mouse_speed) + 1
                    self.uinput.write(ecodes.EV_REL, rel, step if position > 0 else -step)
        if self._deflected(self.scroll_axes):
            for code, rel, sign in zip(self.scroll_axes, (ecodes.REL_HWHEEL, ecodes.REL_WHEEL), (1, -1)):
                position = self.positions.get(code, 0.0)
                if abs(position) < MOUSE_DEADZONE:
                    self.scroll_remainder.pop(code, None)
                    continue
                notches = self.scroll_remainder.get(code, 0.0) + sign * position * abs(position) * SCROLL_NOTCHES_PER_SECOND * elapsed
                whole = int(notches)
                self.scroll_remainder[code] = notches - whole
                if whole:
                    self.uinput.write(ecodes.EV_REL, rel, whole)
        self.uinput.syn()

    def release_buttons(self) -> None:
        for action in list(self.active):
            self._send(list(reversed(action.keys)), 0)
        self.active.clear()
        self.pressed.clear()

    def release_all(self) -> None:
        self.release_buttons()
        self.positions.clear()


def device_maps() -> dict[str, tuple[list[dict], float]]:
    data = load_maps()
    speed = float(data.get('mouse_speed', MOUSE_SPEED_AT_DEFAULT_LEVEL))
    return {path: (entries, speed) for path, entries in data.get('devices', {}).items()}
