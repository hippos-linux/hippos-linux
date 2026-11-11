from __future__ import annotations

import configparser
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

PORTS_DIR = Path('/userdata/roms/ports')
CLAIMS = Path('/userdata/system/ports-apt-claims')

_LAUNCHER_TEMPLATE = """\
#!/bin/bash
# HippOS port: {name}
{marker}export HOME=/userdata
export XDG_CONFIG_HOME=/userdata/system/.config
export XDG_DATA_HOME=/userdata/system/.local/share
exec {command}
"""

_FIELD_CODE = re.compile(r'\s*%[fFuUdDnNickvm]')

@dataclass(frozen=True)
class DesktopApp:
    name: str
    command: str
    categories: frozenset[str]
    comment: str | None = None
    icon: str | None = None

def read_desktop_file(path: Path) -> DesktopApp | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(path, encoding='utf-8')
    except (configparser.Error, UnicodeDecodeError):
        return None
    if not parser.has_section('Desktop Entry'):
        return None
    entry = parser['Desktop Entry']
    if entry.get('Type', 'Application') != 'Application':
        return None
    if entry.get('NoDisplay') == 'true' or entry.get('Hidden') == 'true':
        return None
    command = _FIELD_CODE.sub('', entry.get('Exec', '')).replace('%%', '%').strip()
    if not command:
        return None
    return DesktopApp(
        name=entry.get('Name', path.stem),
        command=command,
        categories=frozenset(c for c in entry.get('Categories', '').split(';') if c),
        comment=entry.get('Comment') or None,
        icon=entry.get('Icon') or None,
    )

def launcher_path(name: str) -> Path:
    slug = re.sub(r'[^A-Za-z0-9._ -]', '', name).strip().replace(' ', '_')
    return PORTS_DIR / f'{slug or "port"}.sh'

def write_launcher(path: Path, name: str, command: str, marker: str = '') -> None:
    created_dir = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _LAUNCHER_TEMPLATE.format(name=name, command=command, marker=f'# {marker}\n' if marker else ''),
        encoding='utf-8',
    )
    path.chmod(0o755)
    _own_like_parent(([path.parent] if created_dir else []) + [path], path.parent.parent)

def _own_like_parent(paths: list[Path], parent: Path) -> None:
    if os.getuid() != 0:
        return
    owner = parent.stat()
    for path in paths:
        os.chown(path, owner.st_uid, owner.st_gid)

def claimed_packages() -> set[str]:
    try:
        return set(CLAIMS.read_text(encoding='utf-8').split())
    except FileNotFoundError:
        return set()

def set_claimed(packages: list[str], claimed: bool) -> None:
    current = claimed_packages()
    updated = current | set(packages) if claimed else current - set(packages)
    if updated == current:
        return
    existed = CLAIMS.exists()
    CLAIMS.write_text(''.join(f'{p}\n' for p in sorted(updated)), encoding='utf-8')
    if not existed:
        _own_like_parent([CLAIMS], CLAIMS.parent)

def read_marker(path: Path, prefix: str) -> list[str] | None:
    try:
        with path.open(encoding='utf-8') as f:
            for line in f:
                if line.startswith(f'# {prefix} '):
                    return shlex.split(line[len(prefix) + 3:])
                if not line.startswith('#'):
                    return None
    except (OSError, UnicodeDecodeError):
        pass
    return None
