"""Keep a ROM folder of one-line launcher files in step with a game library.

Used by hippos-steam-sync, hippos-heroic-sync and hippos-lutris-sync. Each
launcher file holds the key its launcher needs (Steam appid, Heroic
platform:app_name, Lutris game id); a state file maps keys to file paths so
renamed or removed games can be tracked without touching user-made files.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# hippos:users, so the user can manage the generated files.
_OWNER_UID, _OWNER_GID = 1000, 100


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
    """games: key -> display name. Returns (created, updated, removed).

    A name that's taken by another game's file, or is one of reserved_stems,
    gets " (key)" appended."""
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
        taken = candidate in claimed or _read_key(candidate) not in (None, key)
        if stem in reserved_stems or taken:
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
            pass  # not root (e.g. run by hand as the user): already owned right
    return created, updated, removed
