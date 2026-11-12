from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path

from hippos_appstream import hicolor_icon

_FIELD_CODE = re.compile(r'\s*%[fFuUdDnNickvm]')
_ICON_SHARES = (Path('/userdata/.local/share'), Path('/userdata/system/.local/share'), Path('/usr/share'))
_PIXMAPS = Path('/usr/share/pixmaps')

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

def find_icon(icon: str | None) -> Path | None:
    if not icon:
        return None
    if icon.startswith('/'):
        return Path(icon) if Path(icon).is_file() else None
    for share in _ICON_SHARES:
        if found := hicolor_icon(share, icon):
            return found
    return next((path for path in (_PIXMAPS / f'{icon}.png', _PIXMAPS / f'{icon}.svg') if path.is_file()), None)
