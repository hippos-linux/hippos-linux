from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
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
    netplay_announce: str = 'launcher'
    netplay_upnp: bool = True

    @property
    def binary_names(self) -> tuple[str, ...]:
        return self.binaries or (self.name,)

    @property
    def hotkey_context(self) -> str:
        return self.hotkeys or self.name


_EMULATORS: dict[str, Emulator] = {}
_SOURCE_OF: dict[str, str] = {}
_BUILTIN_DIR = Path(__file__).resolve().parent


@dataclass
class _LauncherSources:
    packages_root: Optional[Path] = None
    index_file: Optional[Path] = None
    index: Optional[dict[str, str]] = None
    all_loaded: bool = False


_sources = _LauncherSources()


def register(emulator: Emulator) -> Emulator:
    if emulator.name in _EMULATORS:
        raise ValueError(f"emulator '{emulator.name}' is registered twice")
    _EMULATORS[emulator.name] = emulator
    _SOURCE_OF[emulator.name] = str(Path(sys._getframe(1).f_globals.get('__file__', '')).resolve())
    return emulator


def use_launcher_sources(packages_root: Path, index_file: Optional[Path]) -> None:
    _sources.packages_root = packages_root
    _sources.index_file = index_file
    _sources.index = None
    _sources.all_loaded = False


def registered() -> Mapping[str, Emulator]:
    load_all_launchers()
    return MappingProxyType(_EMULATORS)


def lookup(name: str) -> Optional[Emulator]:
    if name not in _EMULATORS and not _sources.all_loaded:
        _load_launcher_for(name)
    return _EMULATORS.get(name)


def load_all_launchers() -> None:
    if _sources.all_loaded:
        return
    sources = _launcher_sources()
    for path in sources:
        _load_source(path)
    _sources.all_loaded = True
    _save_index(sources)


def _load_launcher_for(name: str) -> None:
    if _sources.index is None:
        _sources.index = _read_index()
    if _sources.index is None:
        load_all_launchers()
        return
    source = _sources.index.get(name)
    if source is not None:
        _load_source(Path(source))
    if name not in _EMULATORS and source is not None:
        load_all_launchers()


def _launcher_sources() -> list[Path]:
    sources = sorted(_BUILTIN_DIR.glob('emulatorlauncher_*.py'))
    if _sources.packages_root is not None:
        sources += [path.resolve() for path in sorted(_sources.packages_root.glob('*/hippos/launcher/*.py'))
                    if not path.parents[2].name.endswith('.new')]
    return sources


def _source_stamps(sources: list[Path]) -> dict[str, int]:
    return {str(path): path.stat().st_mtime_ns for path in sources}


def _read_index() -> Optional[dict[str, str]]:
    if _sources.index_file is None:
        return None
    try:
        saved = json.loads(_sources.index_file.read_text(encoding='utf-8'))
        if saved['sources'] != _source_stamps(_launcher_sources()):
            return None
        return saved['emulators']
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _save_index(sources: list[Path]) -> None:
    if _sources.index_file is None:
        return
    stamps = _source_stamps(sources)
    content = json.dumps({
        'sources': stamps,
        'emulators': {name: _SOURCE_OF[name] for name in sorted(_EMULATORS) if _SOURCE_OF[name] in stamps},
    }, indent=1)
    tmp = _sources.index_file.with_name(f'.{_sources.index_file.name}.{os.getpid()}')
    try:
        _sources.index_file.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(content, encoding='utf-8')
        os.replace(tmp, _sources.index_file)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        logging.getLogger('emulatorlauncher').warning("Could not save the emulator launcher index %s: %s",
                                                      _sources.index_file, exc)
    _sources.index = None


def _load_source(path: Path) -> None:
    name = path.stem
    if path.resolve().parent == _BUILTIN_DIR:
        importlib.import_module(name)
        return
    if name in sys.modules:
        if getattr(sys.modules[name], '__file__', None) != str(path):
            logging.getLogger('emulatorlauncher').error(
                "Skipping %s: a module named %s is already loaded", path, name)
        return
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        logging.getLogger('emulatorlauncher').exception("Could not load emulator package launcher %s", path)
