#!/usr/bin/env python3
"""Usage: hippos-led model
       hippos-led daemon
       hippos-led rainbow | chroma | pulse
       hippos-led set_color_dec R G B | set_color_force_dec R G B
       hippos-led set_brightness PERCENT
       hippos-led block_color_changes | unblock_color_changes
       hippos-led battery_profile

Settings (hippos.conf):
  led.enabled            0 turns the LEDs off
  led.mode               static, rainbow, chroma, pulse or battery
  led.colour             "R G B", the static colour
  led.brightness         0-100
  led.battery.levels     battery mode colours, as percent:colour pairs, e.g. 0:BLINK_FF0000,5:FF0000,20:FF5000,40:FFC800,60:00FF00
  led.battery.charging   colour while charging: PULSE (pulse the level colour), LEVEL or a colour
  led.battery.full       colour when full: a colour, PULSE or LEVEL
A colour is RRGGBB, BLINK_RRGGBB, PULSE_RRGGBB or OFF.
"""
from __future__ import annotations

import colorsys
import glob
import os
import sys
import time
from pathlib import Path

import hippos_settings

BLOCK_FILE = Path('/run/hippos/led-block')
BLOCK_SECONDS = 120
FRAME_SECONDS = 0.1
IDLE_SECONDS = 3
RAINBOW_SECONDS = 2
CHROMA_CYCLE_SECONDS = 15
PULSE_SECONDS = 2
BLINK_SECONDS = 1
DEFAULT_COLOUR = (255, 0, 165)
BATTERY_LEVELS = '0:BLINK_FF0000,5:FF0000,20:FF5000,40:FFC800,60:00FF00'
EFFECT_MODES = ('rainbow', 'chroma', 'pulse')


def _read(path: str) -> str:
    with open(path) as f:
        return f.read().strip()


def _write(path: str, value: object) -> None:
    with open(path, 'w') as f:
        f.write(str(value))


class Settings:
    def __init__(self) -> None:
        self._stamp: tuple = ()
        self._values: dict[str, str] = {}

    def get(self, key: str, default: str = '') -> str:
        stamp = tuple(p.stat().st_mtime_ns if p.exists() else 0
                      for p in (hippos_settings.DEFAULTS_CONF, hippos_settings.HW_DEFAULTS, hippos_settings.USER_CONF))
        if stamp != self._stamp:
            self._values, self._stamp = hippos_settings.merged(), stamp
        return self._values.get(key) or default

    @property
    def brightness(self) -> int:
        try:
            return max(0, min(100, int(float(self.get('led.brightness', '100')))))
        except ValueError:
            return 100

    @property
    def colour(self) -> tuple[int, int, int]:
        return parse_colour(self.get('led.colour')) or DEFAULT_COLOUR


def parse_colour(text: str) -> tuple[int, int, int] | None:
    parts = text.split()
    try:
        if len(parts) == 3:
            return tuple(max(0, min(255, int(p))) for p in parts)  # type: ignore[return-value]
        if len(text) == 6:
            return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        pass
    return None


class Led:
    native_effects: dict[str, object] = {}

    def write(self, rgb: tuple[int, int, int], brightness: int) -> None:
        raise NotImplementedError

    def native_effect(self, effect: str, rgb: tuple[int, int, int], brightness: int) -> None:
        raise NotImplementedError

    def off(self) -> None:
        self.write((0, 0, 0), 0)


class SingleRgbLed(Led):
    def __init__(self, path: str) -> None:
        self.path = path

    def write(self, rgb, brightness):
        _write(f'{self.path}/brightness', round(brightness / 100 * int(_read(f'{self.path}/max_brightness'))))
        _write(f'{self.path}/multi_intensity', ' '.join(map(str, rgb)))


class RingLeds(Led):
    def __init__(self, paths: list[str]) -> None:
        self.paths = paths
        try:
            self.order = _read(f'{paths[0]}/multi_index').split()
        except OSError:
            self.order = ['red', 'green', 'blue']

    def write(self, rgb, brightness):
        channels = dict(zip(('red', 'green', 'blue'), rgb))
        intensity = ' '.join(str(channels.get(c, 0)) for c in self.order)
        level = round(brightness / 100 * 255)
        for path in self.paths:
            if _read(f'{path}/brightness') != str(level):
                _write(f'{path}/brightness', level)
            _write(f'{path}/multi_intensity', intensity)


class AddressableLeds(Led):
    def __init__(self) -> None:
        self.channels = [sorted(glob.glob(f'/sys/class/leds/[lr]:{c}[0-9]*')) for c in 'rgb']
        self.max = int(_read(f'{self.channels[0][0]}/max_brightness'))

    def write(self, rgb, brightness):
        for paths, value in zip(self.channels, rgb):
            for path in paths:
                _write(f'{path}/brightness', round(value / 255 * brightness / 100 * self.max))


class MonochromeLeds(Led):
    PATHS = ['/sys/class/leds/left_joystick', '/sys/class/leds/right_joystick',
             '/sys/class/leds/left_side', '/sys/class/leds/right_side']

    def __init__(self) -> None:
        for path in self.PATHS:
            if os.path.exists(path):
                _write(f'{path}/trigger', 'none')

    def write(self, rgb, brightness):
        on = int(any(rgb) and brightness > 0)
        for path in self.PATHS:
            if os.path.exists(path):
                _write(f'{path}/brightness', on)


class LegionGoLeds(Led):
    native_effects = {'rainbow': 'rainbow', 'chroma': 'chroma', 'pulse': 'breathe'}

    def __init__(self, prefix: str) -> None:
        self.path = f'/sys/class/leds/{prefix}:rgb:joystick_rings'
        _write(f'{self.path}/mode', 'custom')
        _write(f'{self.path}/speed', 100)

    def _on(self, brightness):
        _write(f'{self.path}/enabled', 'true')
        _write(f'{self.path}/brightness', round(brightness / 100 * int(_read(f'{self.path}/max_brightness'))))

    def write(self, rgb, brightness):
        if not any(rgb) or brightness == 0:
            self.off()
            return
        self._on(brightness)
        _write(f'{self.path}/effect', 'monocolor')
        _write(f'{self.path}/multi_intensity', ' '.join(map(str, rgb)))

    def native_effect(self, effect, rgb, brightness):
        self._on(brightness)
        _write(f'{self.path}/effect', self.native_effects[effect])

    def off(self):
        _write(f'{self.path}/enabled', 'false')
        _write(f'{self.path}/brightness', 0)


class R36UltraLeds(Led):
    PATH = '/sys/class/leds/keros::ambient/brightness'
    PRESETS = {(0, 0, 0): 0, (1, 0, 0): 1, (1, 1, 0): 2, (0, 1, 0): 3,
               (0, 1, 1): 4, (0, 0, 1): 5, (1, 0, 1): 6, (1, 1, 1): 7}
    native_effects = {'pulse': 8, 'rainbow': 9, 'chroma': 9}

    def write(self, rgb, brightness):
        preset = tuple(int(c >= 128) for c in rgb) if brightness > 0 else (0, 0, 0)
        _write(self.PATH, self.PRESETS[preset])

    def native_effect(self, effect, rgb, brightness):
        _write(self.PATH, self.native_effects[effect])


class VitaProLeds(Led):
    def __init__(self) -> None:
        self.rings = sorted(glob.glob('/sys/class/leds/*::joystick-left') + glob.glob('/sys/class/leds/*::joystick-right'))
        self.mcu = os.path.realpath(f'{self.rings[0]}/device')
        _write(f'{self.mcu}/led_switch', 1)

    def write(self, rgb, brightness):
        _write(f'{self.mcu}/led_mode', 5)
        for ring in self.rings:
            _write(f'{ring}/brightness', round(brightness / 100 * 255))
            _write(f'{ring}/multi_intensity', ' '.join(map(str, rgb)))


class CubeXXLeds(Led):
    POWER = '/sys/class/leds/rgb:kbd_backlight/brightness'
    LEDS_PER_RING = 8
    STATIC, PULSE, CHROMA, RAINBOW = 1, 3, 5, 6
    native_effects = {'pulse': PULSE, 'chroma': CHROMA, 'rainbow': RAINBOW}

    def __init__(self, serial: str) -> None:
        self.serial = serial
        os.system(f'stty -F {serial} 115200 -opost -isig -icanon -echo')

    def _send(self, mode, rgb, brightness):
        _write(self.POWER, 1)
        packet = bytearray([mode, round(brightness / 100 * 255)]) + bytearray(rgb) * (2 * self.LEDS_PER_RING)
        packet.append(sum(packet) & 0xff)
        with open(self.serial, 'wb') as f:
            f.write(packet)

    def write(self, rgb, brightness):
        if not any(rgb) or brightness == 0:
            self.off()
            return
        self._send(self.STATIC, rgb, brightness)

    def native_effect(self, effect, rgb, brightness):
        self._send(self.native_effects[effect], rgb, brightness)

    def off(self):
        self._send(self.STATIC, (0, 0, 0), 0)
        _write(self.POWER, 0)


class RG55G1Leds(Led):
    BASE = '/sys/devices/platform/singleadc-joypad'

    def write(self, rgb, brightness):
        _write(f'{self.BASE}/led_level', brightness)
        for channel, value in zip('rgb', rgb):
            _write(f'{self.BASE}/custum_rgb_{channel}', value)
        _write(f'{self.BASE}/led_mode', 1)
        _write(f'{self.BASE}/led_set', 1)


def _h700_led_serial() -> str | None:
    for tty in glob.glob('/sys/class/tty/ttyS*'):
        if '/5001400.serial' in os.path.realpath(f'{tty}/device'):
            return f'/dev/{os.path.basename(tty)}'
    return None


def find_led() -> tuple[str, Led] | None:
    if glob.glob('/sys/class/leds/*::joystick-left'):
        return 'rg_vita_pro', VitaProLeds()
    if os.path.exists('/sys/class/leds/rgb:kbd_backlight/brightness') \
            and not os.path.exists('/sys/class/leds/rgb:kbd_backlight/multi_intensity') \
            and (serial := _h700_led_serial()):
        return 'cubexx', CubeXXLeds(serial)
    if os.path.exists('/sys/class/leds/left_joystick/brightness'):
        return 'monochrome', MonochromeLeds()
    rings = sorted(glob.glob('/sys/class/leds/rgb:[lr][0-9]*')) \
        or sorted(glob.glob('/sys/devices/platform/multi-led*/leds/rgb:[lr][0-9]*'))
    if rings:
        return 'multiled', RingLeds(rings)
    for prefix, name in (('go_s', 'legiongos'), ('go', 'legiongo')):
        if os.path.exists(f'/sys/class/leds/{prefix}:rgb:joystick_rings/effect'):
            return name, LegionGoLeds(prefix)
    if single := glob.glob('/sys/class/leds/*:rgb:joystick_rings') or glob.glob('/sys/class/leds/multicolor:chassis'):
        return 'rgb', SingleRgbLed(single[0])
    if os.path.exists(R36UltraLeds.PATH):
        return 'r36ultra', R36UltraLeds()
    if glob.glob('/sys/class/leds/[lr]:b[0-9]*'):
        return 'addressable', AddressableLeds()
    if os.path.exists(f'{RG55G1Leds.BASE}/led_switch'):
        return 'rg55g1', RG55G1Leds()
    return None


def rainbow_colour(position: float) -> tuple[int, int, int]:
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(position % 1.0, 1.0, 1.0))  # type: ignore[return-value]


def pulse_colour(rgb: tuple[int, int, int], now: float) -> tuple[int, int, int]:
    phase = (now % PULSE_SECONDS) / PULSE_SECONDS
    level = abs(1 - 2 * phase)
    return tuple(round(c * level) for c in rgb)  # type: ignore[return-value]


def blocked() -> bool:
    try:
        return time.time() - float(BLOCK_FILE.read_text()) < BLOCK_SECONDS
    except (OSError, ValueError):
        return False


def set_blocked(block: bool) -> None:
    BLOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    BLOCK_FILE.write_text(str(time.time()) if block else '0')


def _battery() -> tuple[int, str] | None:
    for supply in sorted(glob.glob('/sys/class/power_supply/*')):
        try:
            if _read(f'{supply}/type') == 'Battery' and os.path.exists(f'{supply}/capacity'):
                return int(_read(f'{supply}/capacity')), _read(f'{supply}/status')
        except (OSError, ValueError):
            continue
    return None


def battery_profile(settings: Settings) -> tuple[list[tuple[int, str]], str, str]:
    levels = []
    for value in (settings.get('led.battery.levels'), BATTERY_LEVELS):
        for item in value.split(','):
            level, _, colour = item.strip().partition(':')
            if level.isdigit() and int(level) <= 100 and colour:
                levels.append((int(level), colour))
        if levels:
            break
    return sorted(levels), settings.get('led.battery.charging', 'PULSE'), settings.get('led.battery.full', 'BLINK_00FF00')


def battery_action(settings: Settings, capacity: int, status: str) -> str:
    levels, charging, full = battery_profile(settings)
    level_colour = next((c for level, c in reversed(levels) if capacity >= level), 'OFF')
    if status == 'Full' or (status == 'Charging' and capacity >= 100):
        plugged = full
    elif status == 'Charging':
        plugged = charging
    else:
        return level_colour
    if plugged == 'LEVEL':
        return level_colour
    if plugged == 'PULSE':
        base = level_colour.rpartition('_')[2]
        return f'PULSE_{base}' if len(base) == 6 else level_colour
    return plugged


def action_colour(action: str, now: float) -> tuple[int, int, int]:
    effect, _, hex_colour = action.rpartition('_')
    rgb = parse_colour(hex_colour) or (0, 0, 0)
    if effect == 'BLINK':
        return rgb if now % BLINK_SECONDS < BLINK_SECONDS / 2 else (0, 0, 0)
    if effect == 'PULSE':
        return pulse_colour(rgb, now)
    return rgb


def effect_frame(effect: str, settings: Settings, now: float) -> tuple[int, int, int]:
    if effect == 'rainbow':
        return rainbow_colour(now / RAINBOW_SECONDS)
    if effect == 'chroma':
        return rainbow_colour(now / CHROMA_CYCLE_SECONDS)
    return pulse_colour(settings.colour, now)


def play_effect(led: Led, effect: str, settings: Settings) -> None:
    if effect in led.native_effects:
        led.native_effect(effect, settings.colour, settings.brightness)
        return
    set_blocked(True)
    try:
        end = time.monotonic() + (CHROMA_CYCLE_SECONDS if effect == 'chroma' else RAINBOW_SECONDS)
        while time.monotonic() < end:
            led.write(effect_frame(effect, settings, time.monotonic()), settings.brightness)
            time.sleep(FRAME_SECONDS)
    finally:
        set_blocked(False)
    if settings.get('led.mode', 'static') not in EFFECT_MODES + ('battery',):
        led.write(settings.colour, settings.brightness)


def run_daemon(led: Led, settings: Settings) -> None:
    shown = None
    while True:
        mode = settings.get('led.mode', 'static')
        if settings.get('led.enabled', '1') == '0' or blocked() or mode not in EFFECT_MODES + ('battery',):
            shown = None
            time.sleep(IDLE_SECONDS)
            continue
        if mode in led.native_effects:
            if shown != (mode, settings.colour, settings.brightness):
                led.native_effect(mode, settings.colour, settings.brightness)
                shown = (mode, settings.colour, settings.brightness)
            time.sleep(IDLE_SECONDS)
            continue
        if mode in EFFECT_MODES:
            led.write(effect_frame(mode, settings, time.monotonic()), settings.brightness)
            shown = None
            time.sleep(FRAME_SECONDS)
            continue
        battery = _battery()
        if battery is None:
            time.sleep(IDLE_SECONDS)
            continue
        action = battery_action(settings, *battery)
        if action.startswith(('BLINK_', 'PULSE_')):
            end = time.monotonic() + IDLE_SECONDS
            while time.monotonic() < end and not blocked():
                led.write(action_colour(action, time.monotonic()), settings.brightness)
                time.sleep(FRAME_SECONDS)
            shown = None
        else:
            if shown != (action, settings.brightness):
                led.write(action_colour(action, 0), settings.brightness)
                shown = (action, settings.brightness)
            time.sleep(IDLE_SECONDS)


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ''
    settings = Settings()
    if command == 'battery_profile':
        levels, charging, full = battery_profile(settings)
        for level, colour in levels:
            print(f'{level}={colour}')
        print(f'charging={charging}')
        print(f'full={full}')
        return 0
    if command in ('block_color_changes', 'unblock_color_changes'):
        set_blocked(command == 'block_color_changes')
        return 0

    found = find_led()
    if found is None:
        print('No supported LEDs', file=sys.stderr)
        return 0 if command == 'daemon' else 1
    model, led = found

    if command == 'model':
        print(model)
    elif command == 'daemon':
        run_daemon(led, settings)
    elif command in EFFECT_MODES:
        if not blocked():
            play_effect(led, command, settings)
    elif command in ('set_color_dec', 'set_color_force_dec') and (rgb := parse_colour(' '.join(argv[2:5]))):
        if command == 'set_color_force_dec' or not blocked():
            led.write(rgb, settings.brightness)
    elif command == 'set_brightness' and len(argv) > 2 and argv[2].isdigit():
        led.write(settings.colour, max(0, min(100, int(argv[2]))))
    else:
        print(__doc__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] not in ('model', 'battery_profile') and os.geteuid() != 0:
        os.execvp('sudo', ['sudo', '-n', sys.executable, os.path.realpath(__file__), *sys.argv[1:]])
    sys.exit(main(sys.argv))
