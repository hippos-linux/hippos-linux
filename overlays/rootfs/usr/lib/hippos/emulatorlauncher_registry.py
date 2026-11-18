from __future__ import annotations

from dataclasses import dataclass
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
