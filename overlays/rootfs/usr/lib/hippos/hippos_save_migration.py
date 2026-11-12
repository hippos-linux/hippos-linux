from __future__ import annotations

import logging
import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from libretro_cores import core_file_names

INFO_DIR = Path('/usr/share/libretro/info')
ES_SYSTEMS = Path('/usr/share/emulationstation/es_systems.cfg')
SAVES = Path('/userdata/saves')
ROMS = Path('/userdata/roms')
USERDATA = Path('/userdata')
RETROARCH_EMULATORS = frozenset({'libretro', 'retroarch'})

_log = logging.getLogger('hippos-save-migration')

def library_name(core: str, info_dir: Path = INFO_DIR) -> str | None:
    for filename in core_file_names(core):
        info = info_dir / filename.replace('.so', '.info')
        try:
            text = info.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        if match := re.search(r'^corename\s*=\s*"([^"]*)"', text, re.M):
            return match.group(1)
    return None

def systems_by_library(es_systems: Path = ES_SYSTEMS, info_dir: Path = INFO_DIR) -> dict[str, set[str]]:
    systems: dict[str, set[str]] = {}
    for system in ET.parse(es_systems).getroot().iter('system'):
        name = system.findtext('name')
        for emulator in system.iter('emulator'):
            if emulator.get('name') not in RETROARCH_EMULATORS:
                continue
            for core in emulator.iter('core'):
                if name and core.text and (library := library_name(core.text.strip(), info_dir)):
                    systems.setdefault(library, set()).add(name)
    return systems

def rom_stems(system_roms: Path) -> set[str]:
    return {path.stem for path in system_roms.rglob('*') if path.is_file()} if system_roms.is_dir() else set()

def owning_system(save: Path, candidates: dict[str, set[str]]) -> str | None:
    matches = [system for system, stems in candidates.items()
               if any(save.name.startswith((f'{stem}.', f'{stem}-')) for stem in stems)]
    return matches[0] if len(matches) == 1 else None

def move_retroarch_core_folders(saves: Path = SAVES, roms: Path = ROMS, es_systems: Path = ES_SYSTEMS,
                                info_dir: Path = INFO_DIR) -> None:
    by_library = systems_by_library(es_systems, info_dir)
    all_systems = set().union(*by_library.values()) if by_library else set()
    for folder in sorted(saves.iterdir()):
        if not folder.is_dir() or folder.name in all_systems or folder.name not in by_library:
            continue
        candidates = {system: rom_stems(roms / system) for system in sorted(by_library[folder.name])}
        for save in sorted(folder.iterdir()):
            if save.is_dir():
                _log.warning('left %s: folder inside a core save folder', save)
                continue
            system = owning_system(save, candidates)
            target = saves / system / save.name if system else None
            if target is None or target.exists():
                _log.warning('left %s: %s', save, 'target exists' if target else 'no single matching system')
                continue
            move(save, target, saves)
        if not any(folder.iterdir()):
            folder.rmdir()

def _own_like(path: Path, root: Path) -> None:
    owner = root.stat()
    for item in (path, *(path.rglob('*') if path.is_dir() else ())):
        os.chown(item, owner.st_uid, owner.st_gid, follow_symlinks=False)

def move(source: Path, target: Path, saves: Path) -> None:
    created = next((parent for parent in reversed(target.parents) if not parent.exists()), None)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(source, target)
    except OSError as error:
        _log.warning('left %s: %s', source, error)
        return
    _own_like(created or target, saves)
    _log.info('moved %s -> %s', source, target)

def merge_tree(source: Path, target: Path, saves: Path) -> None:
    if not source.exists() or source.is_symlink():
        return
    if source.is_file():
        if target.exists():
            _log.warning('left %s: %s exists', source, target)
        else:
            move(source, target, saves)
        return
    for child in sorted(source.iterdir()):
        merge_tree(child, target / child.name, saves)
    if not any(source.iterdir()):
        source.rmdir()
    else:
        _log.warning('left %s: not everything could be moved', source)

def mame_state_folders(mame_saves: Path) -> list[Path]:
    keep = {'nvram', 'input', 'state', 'diff', 'comments', 'cfg', 'plugins'}
    return [folder for folder in sorted(mame_saves.iterdir())
            if folder.is_dir() and folder.name not in keep and any(folder.glob('*.sta'))] if mame_saves.is_dir() else []

def move_emulator_folders(userdata: Path = USERDATA) -> None:
    saves = userdata / 'saves'
    configs = userdata / 'system' / 'configs'
    duckstation = configs / 'duckstation'
    for source, target in (
        (duckstation / 'memcards', saves / 'duckstation' / 'memcards'),
        (duckstation / 'savestates', saves / 'duckstation'),
        (userdata / '.local' / 'share' / 'dolphin-emu', saves / 'dolphin-emu'),
        (userdata / '.local' / 'share' / 'flycast', saves / 'dreamcast' / 'flycast'),
        (configs / 'rpcs3' / 'dev_hdd0', saves / 'ps3' / 'rpcs3' / 'dev_hdd0'),
        *((folder, saves / 'mame' / 'state' / folder.name) for folder in mame_state_folders(saves / 'mame')),
    ):
        merge_tree(source, target, saves)

def migrate() -> None:
    move_emulator_folders()
    move_retroarch_core_folders()
