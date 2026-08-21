from __future__ import annotations

import configparser
import filecmp
import json
import logging
import os
import re
import subprocess
import time
import tomllib
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from shutil import copyfile, which
from typing import Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

from hippos_evmapy import evmapy_context

from HipposPaths import (
    CONFIGS, DEFAULTS_DIR, HIPPOS_CONF, HIPPOS_SHARE_DIR, USERDATA, USER_ES_DIR,
)

STANDALONE_BINARIES: dict[str, tuple[str, ...]] = {
    'amiberry': ('amiberry',),
    'applewin': ('qapple', 'applen', 'applewin', 'AppleWin'),
    'cemu': ('Cemu', 'cemu'),
    'easyrpg': ('easyrpg-player', 'easyrpg'),
    'hypseus-singe': ('hypseus',),
    'ikemen': ('Ikemen_GO', 'ikemen'),
    'melonds': ('melonDS', 'melonds'),
    'openbor': ('OpenBOR', 'OpenBOR7530'),
    'pcsx2': ('pcsx2-qt', 'pcsx2'),
    'ppsspp': ('PPSSPPSDL', 'ppsspp'),
    'basilisk2': ('BasiliskII', 'basilisk2'),
    'citron-neo': ('citron-neo', 'citron'),
    'clk': ('clksignal', 'clk'),
    'demul': ('demul',),
    'dosbox_staging': ('dosbox-staging', 'dosbox_staging', 'dosbox'),
    'eka2l1': ('eka2l1_qt', 'eka2l1'),
    'dosboxx': ('dosbox-x', 'dosboxx'),
    'play': ('Play', 'play'),
    'gsplus': ('GSplus', 'gsplus'),
    'samcoupe': ('samcoupe', 'simcoupe'),
    'heroic': ('heroic',),
    'steam': ('steam',),
    'flatpak': ('flatpak',),
    'moonlight': ('moonlight',),
    'wine': ('wine-tkg', 'wine'),
    'lightspark': ('lightspark',),
    'pyxel': ('pyxel',),
    'ruffle': ('ruffle',),
    'solarus': ('solarus-run', 'solarus'),
    'tsugaru': ('Tsugaru_CUI', 'tsugaru'),
    'x16emu': ('x16emu',),
    'xroar': ('xroar',),
    'thextech': ('thextech',),
    'yquake2': ('yquake2',),
    'desmume': ('desmume',),
    'dolphin': ('dolphin-emu', 'dolphin'),
    'dolphin-emu': ('dolphin-emu', 'dolphin'),
    'dosbox': ('dosbox',),
    'dosbox-x': ('dosbox-x',),
    'fsuae': ('fs-uae', 'fsuae'),
    'fceux': ('fceux',),
    'hatari': ('hatari',),
    'mame': ('mame',),
    'mednafen': ('mednafen',),
    'mupen64plus-qt': ('mupen64plus-qt',),
    'nestopia': ('nestopia',),
    'openmsx': ('openmsx',),
    'raze': ('raze',),
    'redream': ('redream',),
    'ryujinx': ('Ryujinx.sh', 'Ryujinx', 'ryujinx'),
    'eden': ('eden',),
    'sugarbox': ('sugarbox', 'SugarboxV2'),
    'tic80': ('tic80',),
    'vita3k': ('Vita3K', 'vita3k'),
    'vpinball': ('VPinballX_GL', 'VPinballX', 'vpinball'),
    'scummvm': ('scummvm',),
    'stella': ('stella',),
    'vice': ('x64', 'x64sc', 'xscpu64', 'xvic', 'x128', 'x64dtv', 'xplus4', 'xpet'),
    'virtualjaguar': ('virtualjaguar',),
}

ARTIFACT_PACKAGE_ALIASES: dict[str, tuple[str, ...]] = {
    'dolphin': ('dolphin-emu',),
    'dosbox_staging': ('dosbox-staging',),
    'dosboxx': ('dosbox-x',),
    'mupen64plus-qt': ('mupen64plus',),
    'pyxel': ('python-pyxel',),
    'solarus': ('solarus-engine',),
}


DEFAULTS_FILE      = DEFAULTS_DIR / 'configgen-defaults.yml'


HIPPOS_DEFAULTS    = HIPPOS_SHARE_DIR / 'hippos-defaults.conf'


HIPPOS_HW_DEFAULTS = Path('/run/hippos/hardware-defaults.conf')


HOTKEY_CONTEXT_DIR  = HIPPOS_SHARE_DIR / 'hotkeys' / 'contexts'


WHEEL_PROXY_BIN     = Path('/usr/lib/hippos/hippos-wheel-proxy')


ES_INPUT_FILES = (
    USER_ES_DIR / 'es_input.cfg',
    Path('/usr/share/emulationstation/es_input.cfg'),
)


_log = logging.getLogger('emulatorlauncher')


@dataclass
class ControllerInfo:
    player:      int
    index:       int  = 0
    guid:        str  = ''
    name:        str  = ''
    device_path: str  = ''
    is_wheel:    bool = False
    wheel_rotation_angle: int = 0
    nb_buttons:  int  = 0
    nb_hats:     int  = 0
    nb_axes:     int  = 0


@dataclass
class LaunchContext:
    system:      str
    rom:         Path
    emulator:    str
    core:        str
    gameinfoxml:  Optional[Path] = None
    lightgun:    bool = False
    wheel:       bool = False
    controllers: list[ControllerInfo] = field(default_factory=list)
    game_wheel:    dict[str, str] = field(default_factory=dict)
    game_gun:      dict[str, str] = field(default_factory=dict)
    resolution:    Optional[tuple[int, int]] = None
    bezel:         Optional[Path] = None
    netplay_mode:  str = ''   # 'host' | 'client' | 'spectator' | ''
    netplay_ip:    str = ''
    netplay_port:  str = ''


@dataclass(frozen=True)
class ESBinding:
    name: str
    type: str
    code: int
    value: int


@dataclass
class ESControllerProfile:
    device_name: str
    device_guid: str
    device_path: str
    inputs: dict[str, ESBinding]


def _load_hippos_conf() -> dict[str, str]:
    return _read_conf_file(HIPPOS_CONF)


def _read_conf_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, _, v = line.partition('=')
                result[k.strip()] = v.strip()
    except OSError as exc:
        _log.warning("Could not read %s: %s", path, exc)
    return result


def _load_effective_hippos_conf() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in (HIPPOS_DEFAULTS, HIPPOS_HW_DEFAULTS, HIPPOS_CONF):
        result.update(_read_conf_file(path))
    return result


def _load_yaml_defaults() -> dict:
    if not _HAS_YAML or not DEFAULTS_FILE.exists():
        return {}
    try:
        data = yaml.safe_load(DEFAULTS_FILE.read_text())
        return data or {}
    except Exception as exc:
        _log.warning("Could not load %s: %s", DEFAULTS_FILE, exc)
        return {}


def _get_yaml_system_options(system: str) -> dict:
    """Return the options block from configgen-defaults.yml for a system."""
    entry = _load_yaml_defaults().get(system)
    if not entry:
        return {}
    return entry.get('options') or {}


def _hud_supported(system: str) -> bool:
    """False if YAML marks this system as hud_support: false."""
    return _get_yaml_system_options(system).get('hud_support', True) is not False


def configure_emulator(rom: Path) -> bool:
    return str(rom) == 'config'


def generate_sdl_game_controller_config(controllers: list[ControllerInfo], ignore_buttons: Optional[list[str]] = None) -> str:
    ignored = {name.strip().lower() for name in (ignore_buttons or [])}
    profiles = _load_es_input_configs()
    lines: list[str] = []
    seen_guids: set[str] = set()

    for ctrl in controllers:
        guid = ctrl.guid.strip()
        if not guid or guid == '-1' or _normalize(guid) in seen_guids:
            continue
        profile = _pick_es_profile(profiles, ctrl)
        if profile is None:
            continue

        mapping = _sdl_controller_mapping(profile, ignored)
        if not mapping:
            continue

        seen_guids.add(_normalize(guid))
        name = (ctrl.name or profile.device_name or 'HippOS Controller').replace(',', ' ').strip()
        fields = [guid, name, 'platform:Linux']
        fields.extend(f'{key}:{value}' for key, value in mapping)
        lines.append(','.join(fields) + ',')

    return '\n'.join(lines)


def _sdl_binding_value(binding: ESBinding, positive: Optional[bool] = None) -> Optional[str]:
    if binding.type == 'button':
        return f'b{binding.code}'
    if binding.type == 'hat':
        return f'h{binding.code}.{abs(binding.value)}'
    if binding.type == 'axis':
        prefix = ''
        if positive is True:
            prefix = '+'
        elif positive is False:
            prefix = '-'
        return f'{prefix}a{binding.code}'
    return None


def _sdl_controller_mapping(
    profile: ESControllerProfile,
    ignored: set[str],
) -> list[tuple[str, str]]:
    button_map = [
        ('a', 'a'),
        ('b', 'b'),
        ('x', 'x'),
        ('y', 'y'),
        ('back', 'select'),
        ('start', 'start'),
        ('leftshoulder', 'pageup'),
        ('rightshoulder', 'pagedown'),
        ('lefttrigger', 'l2'),
        ('righttrigger', 'r2'),
        ('leftstick', 'l3'),
        ('rightstick', 'r3'),
    ]
    axis_map = [
        ('leftx', 'joystick1left'),
        ('lefty', 'joystick1up'),
        ('rightx', 'joystick2left'),
        ('righty', 'joystick2up'),
    ]
    dpad_map = [
        ('dpup', 'up'),
        ('dpdown', 'down'),
        ('dpleft', 'left'),
        ('dpright', 'right'),
    ]

    mapping: list[tuple[str, str]] = []
    for sdl_name, es_name in button_map:
        if es_name in ignored:
            continue
        binding = profile.inputs.get(es_name)
        if binding is None:
            continue
        value = _sdl_binding_value(binding)
        if value is not None:
            mapping.append((sdl_name, value))

    for sdl_name, es_name in axis_map:
        if es_name in ignored:
            continue
        binding = profile.inputs.get(es_name)
        if binding is None:
            continue
        positive = None
        if binding.type == 'axis' and binding.value:
            positive = binding.value > 0
        value = _sdl_binding_value(binding, positive)
        if value is not None:
            mapping.append((sdl_name, value))

    for sdl_name, es_name in dpad_map:
        if es_name in ignored:
            continue
        binding = profile.inputs.get(es_name)
        if binding is None:
            continue
        positive = None
        if binding.type == 'axis' and binding.value:
            positive = binding.value > 0
        value = _sdl_binding_value(binding, positive)
        if value is not None:
            mapping.append((sdl_name, value))

    return mapping


def _normalize(value: str) -> str:
    return ''.join(ch for ch in value.strip().casefold() if ch.isalnum())


def _load_es_input_configs() -> list[ESControllerProfile]:
    es_path = next((path for path in ES_INPUT_FILES if path.exists()), None)
    if es_path is None:
        return []
    try:
        root = ET.parse(es_path).getroot()
    except ET.ParseError as exc:
        _log.warning("Could not parse %s: %s", es_path, exc)
        return []

    configs: list[ESControllerProfile] = []
    for node in root.findall('inputConfig'):
        if node.attrib.get('type') != 'joystick':
            continue
        inputs: dict[str, ESBinding] = {}
        for input_node in node.findall('input'):
            name = (input_node.attrib.get('name') or '').strip().lower()
            type_name = (input_node.attrib.get('type') or '').strip().lower()
            code_text = input_node.attrib.get('id') or input_node.attrib.get('code')
            value_text = input_node.attrib.get('value', '0')
            if not name or not type_name or code_text is None:
                continue
            try:
                code = int(code_text)
                value = int(value_text)
            except ValueError:
                continue
            inputs[name] = ESBinding(name=name, type=type_name, code=code, value=value)
        configs.append(
            ESControllerProfile(
                device_name=node.attrib.get('deviceName', ''),
                device_guid=node.attrib.get('deviceGUID', ''),
                device_path=node.attrib.get('devicePath', ''),
                inputs=inputs,
            )
        )
    return configs


def _pick_es_profile(
    profiles: list[ESControllerProfile],
    ctrl: ControllerInfo,
) -> Optional[ESControllerProfile]:
    normalized_name = _normalize(ctrl.name)
    normalized_guid = _normalize(ctrl.guid)
    normalized_path = _normalize(ctrl.device_path)

    for profile in profiles:
        if _normalize(profile.device_guid) == normalized_guid and _normalize(profile.device_name) == normalized_name:
            return profile
    for profile in profiles:
        if _normalize(profile.device_guid) == normalized_guid:
            return profile
    for profile in profiles:
        if _normalize(profile.device_path) == normalized_path and normalized_path:
            return profile
    for profile in profiles:
        if _normalize(profile.device_name) == normalized_name:
            return profile
    return profiles[0] if profiles else None


def _conf_value(conf: dict[str, str], key: str, default: str = '') -> str:
    value = conf.get(key, default)
    if value is None:
        return default
    value = str(value).strip()
    if not value or value.lower() == 'auto':
        return default
    return value


def _conf_int(conf: dict[str, str], key: str, default: int = 0) -> int:
    value = _conf_value(conf, key, '')
    if not value:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _conf_bool(conf: dict[str, str], key: str, default: bool = False) -> bool:
    value = _conf_value(conf, key, '')
    if not value:
        return default
    return value.lower() in ('1', 'true', 'on', 'enabled', 'yes')


def _new_ini_parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # keep case-sensitive option names
    return parser


def _ensure_section(parser: configparser.ConfigParser, section: str) -> None:
    if not parser.has_section(section):
        parser.add_section(section)


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Path):
        return json.dumps(str(value))
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_toml_value(item) for item in value) + ']'
    raise TypeError(f'Unsupported TOML value type: {type(value)!r}')


def _toml_write_table(fh, table: dict[str, object], prefix: tuple[str, ...] = ()) -> None:
    scalars: list[tuple[str, object]] = []
    nested: list[tuple[str, dict[str, object]]] = []
    for key, value in table.items():
        if isinstance(value, dict):
            nested.append((key, value))
        else:
            scalars.append((key, value))

    if prefix:
        fh.write(f"[{'.'.join(prefix)}]\n")

    for key, value in scalars:
        fh.write(f"{key} = {_toml_value(value)}\n")

    for idx, (key, value) in enumerate(nested):
        if scalars or idx > 0:
            fh.write('\n')
        _toml_write_table(fh, value, prefix + (key,))


def _write_toml(path: Path, config: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fh:
        _toml_write_table(fh, config)


def _read_toml(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        with path.open('rb') as fh:
            return tomllib.load(fh)
    except Exception as exc:
        _log.warning("Could not read %s: %s", path, exc)
        return {}


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for item in value.split('.'):
        try:
            parts.append(int(item))
        except ValueError:
            break
    return tuple(parts)


def _probe_vulkan_version() -> Optional[tuple[int, ...]]:
    vulkaninfo = which('vulkaninfo')
    if vulkaninfo is None:
        return None
    try:
        proc = subprocess.run([vulkaninfo, '--summary'], capture_output=True, text=True, timeout=5, check=False)
    except Exception:
        return None
    output = '\n'.join(part for part in (proc.stdout, proc.stderr) if part)
    for pattern in (
        r'Vulkan Instance Version:\s*([0-9]+(?:\.[0-9]+){1,2})',
        r'Vulkan API Version:\s*([0-9]+(?:\.[0-9]+){1,2})',
        r'Vulkan Version:\s*([0-9]+(?:\.[0-9]+){1,2})',
    ):
        match = re.search(pattern, output)
        if match:
            return _version_tuple(match.group(1))
    return None


def _find_executable(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    preferred_names = (
        'lindbergh-loader',
        'lindbergh-loader.exe',
        'shadps4',
        'shadps4.exe',
        'model2emu',
        'model2emu.exe',
    )
    for name in preferred_names:
        candidate = root / name
        if candidate.exists() and candidate.is_file():
            return candidate
        candidate = root / 'bin' / name
        if candidate.exists() and candidate.is_file():
            return candidate
    for candidate in root.rglob('*'):
        if candidate.is_file():
            try:
                mode = candidate.stat().st_mode
            except OSError:
                continue
            if mode & 0o111:
                return candidate
    return None


def _display_resolution_from_conf(conf: dict[str, str]) -> Optional[tuple[int, int]]:
    value = _conf_value(conf, 'display.resolution', '')
    if not value or value == 'preferred':
        return None
    match = re.match(r'(?P<w>\d+)x(?P<h>\d+)', value)
    if not match:
        return None
    return int(match.group('w')), int(match.group('h'))


def _find_emulator_bin(*names: str) -> Optional[Path]:
    """Find an installed standalone emulator binary.

    Search order matches the runtime resolution policy:
    1. /userdata/emulators/<package>/current/  (user-updated)
    2. /opt/emulators/<package>/                      (OS-bundled artifact)
    """
    for name in names:
        packages = (name,) + ARTIFACT_PACKAGE_ALIASES.get(name, ())
        binaries = STANDALONE_BINARIES.get(name, (name,))
        search_dirs = [
            *(USERDATA / 'emulators' / package / 'current' for package in packages),
            *(Path('/opt/emulators') / package for package in packages),
            *(USERDATA / 'emulators' / package for package in packages),
        ]
        for d in search_dirs:
            for binary in binaries:
                for candidate in (d / binary, d / 'bin' / binary):
                    if candidate.exists() and os.access(str(candidate), os.X_OK):
                        return candidate
        for binary in binaries:
            found = which(binary)
            if found:
                return Path(found)
            for system_dir in (Path('/usr/bin'), Path('/usr/games'), Path('/usr/local/bin')):
                candidate = system_dir / binary
                if candidate.exists() and os.access(str(candidate), os.X_OK):
                    return candidate
    return None


def _find_emulator_bin_in_package(package: str, *binary_names: str) -> Optional[Path]:
    """Find a binary inside a specific emulator package directory."""
    search_dirs = [
        USERDATA / 'emulators' / package / 'current',
        Path('/opt/emulators') / package,
    ]
    for d in search_dirs:
        for binary in binary_names:
            for candidate in (d / binary, d / 'bin' / binary):
                if candidate.exists() and os.access(str(candidate), os.X_OK):
                    return candidate
    for binary in binary_names:
        found = which(binary)
        if found:
            return Path(found)
        for system_dir in (Path('/usr/bin'), Path('/usr/games'), Path('/usr/local/bin')):
            candidate = system_dir / binary
            if candidate.exists() and os.access(str(candidate), os.X_OK):
                return candidate
    return None


HOTKEYS_BIN = Path('/usr/lib/hippos/hippos-hotkeys')


@contextmanager
def hotkey_context(name: str):
    source = HOTKEY_CONTEXT_DIR / f'{name}.json'
    try:
        if source.exists():
            data = json.loads(source.read_text())
            keys: dict[str, object] = data.get('keys', {})

            conf = _load_effective_hippos_conf()
            exit_hotkey_only = conf.get('system.exithotkeyonly', '').lower() in ('1', 'true', 'yes')
            ui_mode = conf.get('system.ui_mode', 'Full')

            if exit_hotkey_only:
                keys = {'exit': keys['exit']} if 'exit' in keys else {}

            if ui_mode.lower() != 'full':
                keys.pop('menu', None)

            cmd = [str(HOTKEYS_BIN), '--new-context', name, json.dumps(keys)]
            if exit_hotkey_only:
                cmd.append('--disable-common')
            # capture_output was previously discarded — --new-context failing
            # (bad json, daemon not running, stale pid) left no trace anywhere,
            # so a stuck-on-previous-context bug looked identical to a working
            # switch from the logs alone.
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                _log.warning("hotkey context '%s' request failed (rc=%s): %s",
                             name, result.returncode, result.stderr.strip())
            else:
                _log.info("hotkey context -> '%s' (keys=%s)", name, sorted(keys))
        else:
            _log.warning("no hotkey context file for '%s' (%s) — daemon stays on whatever context was already active", name, source)
    except Exception as exc:
        _log.warning("Could not set hotkey context '%s': %s", name, exc)

    try:
        yield
    finally:
        try:
            result = subprocess.run(
                [str(HOTKEYS_BIN), '--default-context'],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                _log.warning("hotkey context reset failed (rc=%s): %s",
                             result.returncode, result.stderr.strip())
            else:
                _log.info("hotkey context -> default")
        except Exception as exc:
            _log.warning("Could not reset hotkey context: %s", exc)


def _wheel_proxy_command(ctrl: ControllerInfo, ctx: LaunchContext, env: dict[str, str]) -> list[str]:
    wheel_meta = ctx.game_wheel or {}
    return [
        str(WHEEL_PROXY_BIN),
        '--device-path', ctrl.device_path,
        '--device-guid', ctrl.guid,
        '--device-name', ctrl.name,
        '--device-index', str(ctrl.index),
        '--proxy-name', f'HippOS wheel proxy P{ctrl.player}',
        '--wheel-name', wheel_meta.get('wheel', 'joystick1left'),
        '--accelerate-name', wheel_meta.get('accelerate', 'r2'),
        '--brake-name', wheel_meta.get('brake', 'l2'),
        '--downshift-name', wheel_meta.get('downshift', 'pageup'),
        '--upshift-name', wheel_meta.get('upshift', 'pagedown'),
        '--physical-rotation-angle', str(ctrl.wheel_rotation_angle or 900),
        '--rotation', env.get('HIPPOS_WHEEL_ROTATION', ''),
        '--deadzone', env.get('HIPPOS_WHEEL_DEADZONE', ''),
        '--midzone', env.get('HIPPOS_WHEEL_MIDZONE', ''),
    ]


@contextmanager
def wheel_proxy_context(ctx: LaunchContext, env: dict[str, str]):
    if not ctx.wheel:
        yield
        return

    wheel_procs: list[subprocess.Popen[str]] = []
    try:
        if not WHEEL_PROXY_BIN.exists():
            _log.warning("Wheel proxy helper not found: %s", WHEEL_PROXY_BIN)
            yield
            return

        for ctrl in ctx.controllers:
            if not ctrl.is_wheel or not ctrl.device_path:
                continue
            cmd = _wheel_proxy_command(ctrl, ctx, env)
            _log.info("Starting wheel proxy: %s", ' '.join(cmd))
            proc = subprocess.Popen(cmd, env=env, text=True)
            wheel_procs.append(proc)
            time.sleep(0.15)
            if proc.poll() is not None:
                raise RuntimeError(f"wheel proxy exited early for {ctrl.device_path} with code {proc.returncode}")

        yield
    finally:
        for proc in wheel_procs:
            try:
                proc.terminate()
            except Exception:
                pass
        for proc in wheel_procs:
            try:
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _gamescope_wrap(cmd: list[str], conf: dict[str, str]) -> list[str]:
    if not _conf_bool(conf, 'global.gamescope'):
        return cmd
    bin_path = which('gamescope')
    if bin_path is None:
        _log.warning("gamescope enabled but binary not found")
        return cmd

    gs = [bin_path]

    output_res = _conf_value(conf, 'global.gamescope_output_resolution', '')
    if output_res:
        w, _, h = output_res.partition('x')
        gs += ['-W', w, '-H', h]

    nested_res = _conf_value(conf, 'global.gamescope_nested_resolution', '')
    if nested_res:
        w, _, h = nested_res.partition('x')
        gs += ['-w', w, '-h', h]

    refresh = _conf_value(conf, 'global.gamescope_nested_refresh', '')
    if refresh:
        gs += ['-r', refresh]

    scaler = _conf_value(conf, 'global.gamescope_scaler', '')
    if scaler:
        gs += ['-S', scaler]

    filt = _conf_value(conf, 'global.gamescope_filter', '')
    if filt:
        gs += ['-F', filt]

    sharpness = _conf_value(conf, 'global.gamescope_sharpness', '')
    if sharpness:
        gs += ['--sharpness', sharpness]

    if _conf_bool(conf, 'global.gamescope_hdr'):
        gs.append('--hdr-enabled')

    extra_args = _conf_value(conf, 'global.gamescope_args', '-f -e')
    if extra_args.strip():
        gs += extra_args.split()

    gs.append('--')
    _log.info("gamescope wrap: %s", ' '.join(gs))
    return gs + cmd


def _run_game_command(
    ctx: LaunchContext,
    hotkey_name: str,
    cmd: list[str],
    env: dict[str, str],
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    conf = _load_hippos_conf()
    cmd = _gamescope_wrap(cmd, conf)
    if _hud_config_path() is not None and ctx.emulator in _HUD_NEEDS_WRAPPER and _hud_supported(ctx.system):
        cmd = ['mangohud'] + cmd
    with wheel_proxy_context(ctx, env):
        with hotkey_context(hotkey_name):
            profiles = _load_es_input_configs()
            with evmapy_context(ctx.system, ctx.emulator, ctx.rom, ctx.controllers, profiles):
                return subprocess.run(cmd, env=env, text=True, cwd=str(cwd) if cwd is not None else None)


def _build_game_env(conf: dict[str, str], ctx: Optional[LaunchContext] = None) -> dict[str, str]:
    env = dict(os.environ)
    prime_env = Path('/run/hippos/prime.env')
    if prime_env.exists():
        for line in prime_env.read_text().splitlines():
            line = line.removeprefix('export ').strip()
            if '=' in line:
                k, v = line.split('=', 1)
                env[k] = v
    env.setdefault('DISPLAY', ':0')
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['HIPPOS_USE_GUNS'] = '1' if _conf_bool(conf, 'global.use_guns', True) else '0'
    env['HIPPOS_USE_WHEELS'] = '1' if _conf_bool(conf, 'global.use_wheels', True) else '0'
    env['HIPPOS_WHEEL_ROTATION'] = _conf_value(conf, 'wheel_rotation', '')
    env['HIPPOS_WHEEL_DEADZONE'] = _conf_value(conf, 'wheel_deadzone', '')
    env['HIPPOS_WHEEL_MIDZONE'] = _conf_value(conf, 'wheel_midzone', '')
    if ctx is not None and ctx.game_wheel:
        for key, value in ctx.game_wheel.items():
            env[f'HIPPOS_GAME_WHEEL_{key.upper()}'] = str(value)
        if ctx.game_wheel.get('rotation'):
            env['HIPPOS_WHEEL_ROTATION'] = ctx.game_wheel['rotation']
        if ctx.game_wheel.get('deadzone'):
            env['HIPPOS_WHEEL_DEADZONE'] = ctx.game_wheel['deadzone']
        if ctx.game_wheel.get('midzone'):
            env['HIPPOS_WHEEL_MIDZONE'] = ctx.game_wheel['midzone']
        env['HIPPOS_GAME_WHEEL_PRESENT'] = '1'
    else:
        env['HIPPOS_GAME_WHEEL_PRESENT'] = '0'
    if ctx is not None:
        for ctrl in ctx.controllers:
            prefix = f'HIPPOS_P{ctrl.player}_'
            env[f'{prefix}INDEX'] = str(ctrl.index)
            env[f'{prefix}GUID'] = ctrl.guid
            env[f'{prefix}NAME'] = ctrl.name
            env[f'{prefix}DEVICEPATH'] = ctrl.device_path
            env[f'{prefix}ISWHEEL'] = '1' if ctrl.is_wheel else '0'
            env[f'{prefix}WHEELROTATIONANGLE'] = str(ctrl.wheel_rotation_angle)
            env[f'{prefix}NBBUTTONS'] = str(ctrl.nb_buttons)
            env[f'{prefix}NBHATS'] = str(ctrl.nb_hats)
            env[f'{prefix}NBAXES'] = str(ctrl.nb_axes)
    if ctx is not None and ctx.controllers:
        env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    # Enable SDL2 HIDAPI Steam Controller support (works natively without steamd)
    env.setdefault('SDL_JOYSTICK_HIDAPI_STEAM', '1')
    # Force Xbox controllers to use the kernel xpad driver, not SDL2 HIDAPI.
    # xpad claims the USB device so HIDAPI has no hidraw node to open; SDL2 then
    # tries /dev/bus/usb which hippos cannot write to, silently drops the pad.
    env.setdefault('SDL_JOYSTICK_HIDAPI_XBOX_360', '0')
    env.setdefault('SDL_JOYSTICK_HIDAPI_XBOX_ONE', '0')
    env.setdefault('SDL_JOYSTICK_HIDAPI_XBOX', '0')
    hud_cfg = _hud_config_path()
    if hud_cfg is not None and (ctx is None or _hud_supported(ctx.system)):
        env['MANGOHUD_CONFIGFILE'] = str(hud_cfg)
        env['MANGOHUD_DLSYM'] = '1'
    if _conf_bool(conf, 'global.vkbasalt'):
        env['ENABLE_VKBASALT'] = '1'
    return env


_HUD_CONFIG_PATH = Path('/var/run/hippos/hud.config')


_HUD_NEEDS_WRAPPER: frozenset[str] = frozenset({'wine', 'sh', 'flatpak'})


def _hud_config_path() -> Optional[Path]:
    """Return path to hud.config if HUD is active, else None."""
    conf = _load_hippos_conf()
    mode = conf.get('global.hud', 'none').strip()
    return _HUD_CONFIG_PATH if mode and mode != 'none' else None


def _write_unix_settings_file(path: Path, items: list[tuple[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fh:
        for key, value in items:
            fh.write(f'{key}={value}\n')


def _sync_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    # Guard: destination must not be inside source — syncing a dir into its own
    # subtree causes current/ to appear in source on the next run, then recurse
    # infinitely, eventually hitting PATH_MAX ("File name too long").
    try:
        destination.resolve().relative_to(source.resolve())
        __import__('logging').getLogger('hippos.emulatorlauncher').error(
            "_sync_tree: destination %s is inside source %s — refusing to sync",
            destination, source,
        )
        return
    except ValueError:
        pass
    destination.mkdir(parents=True, exist_ok=True)
    cmp = filecmp.dircmp(source, destination)
    for name in cmp.left_only + cmp.diff_files:
        src_path = source / name
        dst_path = destination / name
        if src_path.is_dir():
            _sync_tree(src_path, dst_path)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            copyfile(src_path, dst_path)
    for name in cmp.common_dirs:
        _sync_tree(source / name, destination / name)


_RA_BTN_MAP: list[tuple[str, str]] = [
    ('a',        'a'),
    ('b',        'b'),
    ('x',        'x'),
    ('y',        'y'),
    ('start',    'start'),
    ('select',   'select'),
    ('pageup',   'l'),        # L1 / LB
    ('pagedown', 'r'),        # R1 / RB
    ('l2',       'l2'),       # L2 / LT — may be axis or button
    ('r2',       'r2'),       # R2 / RT
    ('l3',       'l3'),       # Left stick click
    ('r3',       'r3'),       # Right stick click
]


_HAT_DIR: dict[int, str] = {1: 'up', 2: 'right', 4: 'down', 8: 'left'}


def _ra_binding_value(binding: 'ESBinding') -> str:
    """Return RetroArch config value string for a binding (no quotes)."""
    if binding.type == 'button':
        return str(binding.code)
    if binding.type == 'axis':
        sign = '-' if binding.value < 0 else '+'
        return f'{sign}{binding.code}'
    if binding.type == 'hat':
        direction = _HAT_DIR.get(abs(binding.value), 'up')
        return f'h{binding.code}{direction}'
    return str(binding.code)


def _ra_type_suffix(binding: 'ESBinding') -> str:
    if binding.type == 'hat':
        return 'btn'
    return {'button': 'btn', 'axis': 'axis', 'key': 'key'}.get(binding.type, 'btn')


def _ra_analog_dpad_mode(profile: 'ESControllerProfile', system: str) -> str:
    """Return RetroArch analog_dpad_mode: '1' if dpad is buttons/hats (non-analog), else '0'."""
    if system in ('n64', 'n64dd', 'dreamcast', 'atomiswave', 'naomi', 'naomi2', '3ds'):
        return '0'
    for es_name in ('up', 'down', 'left', 'right'):
        b = profile.inputs.get(es_name)
        if b and b.type in ('button', 'hat'):
            return '1'
    return '0'


def _ra_btn_map_for_ctx(profile: 'ESControllerProfile', system: str, core: str, altlayout: str) -> dict[str, str]:
    """Return ES→RA button name map with all system/core-specific overrides applied."""
    btn_map = {es: ra for es, ra in _RA_BTN_MAP}

    # Fightstick layout: swap shoulder/trigger assignments
    if altlayout == 'fightstick':
        btn_map['pageup']   = 'l2'
        btn_map['pagedown'] = 'l'
        btn_map['l2']       = 'r2'
        btn_map['r2']       = 'r'

    # N64: if controller has no r2, promote pageup→l2 and l2→l (Z button fix)
    if system in ('n64', 'n64dd') and 'r2' not in profile.inputs:
        btn_map['pageup'] = 'l2'
        btn_map['l2']     = 'l'

    # Dreamcast/flycast: same r2-missing fix, plus r1/r2 swap
    if system == 'dreamcast' and core == 'flycast' and 'r2' not in profile.inputs:
        btn_map['pageup']   = 'l2'
        btn_map['l2']       = 'l'
        btn_map['pagedown'] = 'r2'
        btn_map['r2']       = 'r'

    # Yabasanshiro: reversed shoulders
    if core == 'yabasanshiro':
        btn_map['pageup']   = 'r'
        btn_map['pagedown'] = 'l'

    return btn_map
