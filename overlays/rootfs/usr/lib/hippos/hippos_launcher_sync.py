from __future__ import annotations

import json
import os
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_OWNER_UID, _OWNER_GID = 1000, 100
_ES_RELOAD = 'http://127.0.0.1:1234/reloadgames'
APPS_INSTALLING_FLAG = Path('/run/hippos/apps-installing')
CLIENT_ENTRY = '@launcher'

@dataclass(frozen=True)
class GameMetadata:
    name: str
    description: str | None = None
    developer: str | None = None
    image: Path | None = None

def safe_filename(name: str, fallback: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', ' ', name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' .')
    return cleaned or fallback

def _read_key(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return None

def _read_state(state_file: Path) -> dict[str, str]:
    try:
        data = json.loads(state_file.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

def _write_state(state_file: Path, state: dict[str, str]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(state_file)

def sync_launchers(
    roms_dir: Path,
    state_file: Path,
    extension: str,
    games: dict[str, str],
    fallback_name: str,
    reserved_stems: tuple[str, ...] = (),
) -> tuple[int, int, int]:
    roms_dir.mkdir(parents=True, exist_ok=True)
    old_state = _read_state(state_file)
    new_state: dict[str, str] = {}
    claimed: set[Path] = set()
    created = updated = removed = 0

    def path_for(key: str, name: str) -> Path:
        previous = Path(old_state.get(key, ''))
        if previous.name and previous.parent == roms_dir and previous not in claimed:
            return previous
        stem = safe_filename(name, fallback_name)
        candidate = roms_dir / f'{stem}{extension}'
        taken = candidate in claimed or _read_key(candidate) not in (None, '', key)
        if (stem in reserved_stems and key != CLIENT_ENTRY) or taken:
            candidate = roms_dir / f'{stem} ({safe_filename(key, key)}){extension}'
        return candidate

    for key, name in sorted(games.items(), key=lambda item: safe_filename(item[1], fallback_name).lower()):
        path = path_for(key, name)
        claimed.add(path)
        before = _read_key(path) if path.exists() else None
        if before != key:
            path.write_text(key + '\n', encoding='utf-8')
            if before is None:
                created += 1
            else:
                updated += 1
        new_state[key] = str(path)

    for key, old_path_text in old_state.items():
        if key in new_state:
            continue
        old_path = Path(old_path_text)
        if old_path.parent == roms_dir and old_path not in claimed and _read_key(old_path) == key:
            old_path.unlink()
            removed += 1

    _write_state(state_file, new_state)
    for path in (roms_dir, state_file, *map(Path, new_state.values())):
        try:
            os.chown(path, _OWNER_UID, _OWNER_GID)
        except OSError:
            pass
    return created, updated, removed

def _chown_to_owner(*paths: Path) -> None:
    for path in paths:
        try:
            os.chown(path, _OWNER_UID, _OWNER_GID)
        except OSError:
            pass

def _fill_if_empty(game: ET.Element, tag: str, value: str | None) -> bool:
    if not value:
        return False
    element = game.find(tag)
    if element is None:
        element = ET.SubElement(game, tag)
    elif (element.text or '').strip():
        return False
    element.text = value
    return True

def _remove_generated_image(roms_dir: Path, game: ET.Element, stem: str) -> None:
    image = Path(game.findtext('image') or '')
    if image.parent == Path('images') and image.stem == stem:
        (roms_dir / image).unlink(missing_ok=True)

def known_keys(state_file: Path) -> set[str]:
    return set(_read_state(state_file))

def sync_gamelist(roms_dir: Path, state_file: Path, extension: str, games: dict[str, GameMetadata]) -> bool:
    gamelist = roms_dir / 'gamelist.xml'
    try:
        tree = ET.parse(gamelist)
    except FileNotFoundError:
        tree = ET.ElementTree(ET.Element('gameList'))
    except ET.ParseError:
        return False
    root = tree.getroot()
    entries = {game.findtext('path'): game for game in root.findall('game')}
    changed = False

    launchers = _read_state(state_file)
    for key, details in games.items():
        launcher = Path(launchers.get(key, ''))
        if launcher.parent != roms_dir:
            continue
        path = f'./{launcher.name}'
        game = entries.get(path)
        if game is None:
            game = ET.SubElement(root, 'game')
            ET.SubElement(game, 'path').text = path
            entries[path] = game
            changed = True
        changed |= _fill_if_empty(game, 'name', details.name)
        changed |= _fill_if_empty(game, 'desc', details.description)
        changed |= _fill_if_empty(game, 'developer', details.developer)
        if details.image and not (game.findtext('image') or '').strip():
            target = Path('images') / f'{launcher.stem}{details.image.suffix}'
            (roms_dir / 'images').mkdir(exist_ok=True)
            shutil.copyfile(details.image, roms_dir / target)
            _chown_to_owner(roms_dir / 'images', roms_dir / target)
            changed |= _fill_if_empty(game, 'image', f'./{target}')

    for path, game in entries.items():
        if path and path.endswith(extension) and not (roms_dir / path).exists():
            _remove_generated_image(roms_dir, game, Path(path).stem)
            root.remove(game)
            changed = True

    if changed:
        ET.indent(tree)
        temporary = gamelist.with_suffix('.xml.tmp')
        tree.write(temporary, encoding='utf-8', xml_declaration=True)
        _chown_to_owner(temporary)
        temporary.replace(gamelist)
    return changed

def reload_es() -> None:
    if APPS_INSTALLING_FLAG.exists():
        return
    try:
        urllib.request.urlopen(_ES_RELOAD, timeout=2).close()
    except OSError:
        pass
