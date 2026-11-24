from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Mapping, Optional

if TYPE_CHECKING:
    from emulatorlauncher_shared import LaunchContext


@dataclass(frozen=True)
class Emulator:
    name: str
    launch: Callable[[LaunchContext], int]
    binaries: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()
    writes_to_rom: bool = False
    fullscreen_flags: tuple[str, ...] = ()
    hud_wrapper: bool = False
    hotkeys: str = ''
    netplay_port: str = ''

    @property
    def binary_names(self) -> tuple[str, ...]:
        return self.binaries or (self.name,)

    @property
    def hotkey_context(self) -> str:
        return self.hotkeys or self.name


_EMULATORS: dict[str, Emulator] = {}


def register(emulator: Emulator) -> Emulator:
    if emulator.name in _EMULATORS:
        raise ValueError(f"emulator '{emulator.name}' is registered twice")
    _EMULATORS[emulator.name] = emulator
    return emulator


def registered() -> Mapping[str, Emulator]:
    return MappingProxyType(_EMULATORS)


def lookup(name: str) -> Optional[Emulator]:
    return _EMULATORS.get(name)


def load_package_launchers(packages_root: Path) -> None:
    log = logging.getLogger('emulatorlauncher')
    for module_path in sorted(packages_root.glob('*/hippos/launcher/*.py')):
        if module_path.parents[2].name.endswith('.new'):
            continue
        name = module_path.stem
        if name in sys.modules:
            log.error("Skipping %s: a module named %s is already loaded", module_path, name)
            continue
        spec = importlib.util.spec_from_file_location(name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            del sys.modules[name]
            log.exception("Could not load emulator package launcher %s", module_path)
