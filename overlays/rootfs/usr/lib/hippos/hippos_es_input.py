from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Optional

from HipposPaths import CACHE, HIPPOS_ES_DIR, USER_ES_DIR

ES_INPUT_FILES = (
    USER_ES_DIR / 'es_input.cfg',
    HIPPOS_ES_DIR / 'es_input.cfg',
)
ES_PLAYERS_INPUT = Path('/tmp/es_input_players.cfg')
PARSED_CACHE_DIR = CACHE / 'hippos' / 'es-input'
PARSED_CACHE_VERSION = 1
SYS_CLASS_INPUT = Path('/sys/class/input')
ABS_HAT0X = 0x10
ABS_HAT3Y = 0x17
ABS_MISC = 0x28

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

    def _sysfs_device_attr(self, attr: str) -> Optional[str]:
        if not self.device_path:
            return None
        try:
            return (SYS_CLASS_INPUT / Path(os.path.realpath(self.device_path)).name / 'device' / attr).read_text().strip()
        except OSError:
            _log.debug("No sysfs %s for %s", attr, self.device_path)
            return None

    @property
    def evdev_name(self) -> str:
        return self._sysfs_device_attr('name') or self.name

    @property
    def evdev_abs_codes(self) -> tuple[int, ...]:
        bitmap = self._sysfs_device_attr('capabilities/abs')
        if not bitmap:
            return ()
        codes = []
        for word_index, word in enumerate(reversed(bitmap.split())):
            bits = int(word, 16)
            codes += [word_index * 64 + bit for bit in range(64) if bits >> bit & 1]
        return tuple(codes)


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
    normalized_name: str = field(default='', compare=False, repr=False)
    normalized_guid: str = field(default='', compare=False, repr=False)
    normalized_path: str = field(default='', compare=False, repr=False)

    def __post_init__(self) -> None:
        self.normalized_name = _normalize(self.device_name)
        self.normalized_guid = _normalize(self.device_guid)
        self.normalized_path = _normalize(self.device_path)


@dataclass(frozen=True)
class ESProfiles:
    launch: tuple[ESControllerProfile, ...]
    installed_file: Optional[Path]

    def all(self) -> tuple[ESControllerProfile, ...]:
        if self.installed_file is None:
            return self.launch
        return self.launch + _parse_es_input_file(self.installed_file, self.installed_file.stat().st_mtime_ns)


def _normalize(value: str) -> str:
    return ''.join(ch for ch in value.strip().casefold() if ch.isalnum())


def _parse_es_input_xml(path: Path) -> tuple[ESControllerProfile, ...]:
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        _log.warning("Could not parse %s: %s", path, exc)
        return ()

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
    return tuple(configs)


def _parsed_cache_file(path: Path) -> Path:
    import hashlib
    return PARSED_CACHE_DIR / f"{hashlib.sha1(str(path).encode()).hexdigest()[:16]}.pickle"


@cache
def _parse_es_input_file(path: Path, mtime_ns: int) -> tuple[ESControllerProfile, ...]:
    import pickle
    key = (PARSED_CACHE_VERSION, str(path), mtime_ns, path.stat().st_size)
    cache_file = _parsed_cache_file(path)
    try:
        with cache_file.open('rb') as handle:
            cached_key, profiles = pickle.load(handle)
        if cached_key == key:
            return profiles
    except (OSError, EOFError, pickle.UnpicklingError, ValueError, TypeError, AttributeError):
        pass
    profiles = _parse_es_input_xml(path)
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_file.with_suffix(f'.{os.getpid()}.tmp')
        with temporary.open('wb') as handle:
            pickle.dump((key, profiles), handle, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporary, cache_file)
    except OSError as exc:
        _log.debug("Could not cache parsed %s: %s", path, exc)
    return profiles


def _load_es_input_configs() -> ESProfiles:
    launch = _parse_es_input_file(ES_PLAYERS_INPUT, ES_PLAYERS_INPUT.stat().st_mtime_ns) if ES_PLAYERS_INPUT.exists() else ()
    return ESProfiles(launch, next((path for path in ES_INPUT_FILES if path.exists()), None))


def _exact_es_profile(profiles: tuple[ESControllerProfile, ...], ctrl: ControllerInfo) -> Optional[ESControllerProfile]:
    guid, name = _normalize(ctrl.guid), _normalize(ctrl.name)
    return next((profile for profile in profiles
                 if profile.normalized_guid == guid and profile.normalized_name == name), None)


def _pick_es_profile(profiles: ESProfiles, ctrl: ControllerInfo) -> Optional[ESControllerProfile]:
    if exact := _exact_es_profile(profiles.launch, ctrl):
        return exact
    candidates = profiles.all()
    if exact := _exact_es_profile(candidates, ctrl):
        return exact
    normalized_guid = _normalize(ctrl.guid)
    normalized_path = _normalize(ctrl.device_path)
    normalized_name = _normalize(ctrl.name)
    for profile in candidates:
        if profile.normalized_guid == normalized_guid:
            return profile
    for profile in candidates:
        if profile.normalized_path == normalized_path and normalized_path:
            return profile
    for profile in candidates:
        if profile.normalized_name == normalized_name:
            return profile
    return candidates[0] if candidates else None
