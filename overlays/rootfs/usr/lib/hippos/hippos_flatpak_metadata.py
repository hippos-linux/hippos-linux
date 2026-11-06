"""Read an installed app's own AppStream description and icon, with no network access."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_INSTALL_ROOTS = (Path('/userdata/.local/share/flatpak/app'), Path('/var/lib/flatpak/app'))
_LANG = '{http://www.w3.org/XML/1998/namespace}lang'


@dataclass(frozen=True)
class AppDetails:
    description: str | None = None
    developer: str | None = None
    icon: Path | None = None


def _text(element: ET.Element) -> str:
    return re.sub(r'\s+', ' ', ''.join(element.itertext())).strip()


def _untranslated(parent: ET.Element | None, tag: str) -> ET.Element | None:
    if parent is None:
        return None
    return next((child for child in parent.findall(tag) if _LANG not in child.attrib), None)


def _description(component: ET.Element) -> str | None:
    lines: list[str] = []
    description = _untranslated(component, 'description')
    if description is not None:
        for block in description:
            if _LANG in block.attrib:
                continue
            if block.tag == 'p':
                lines.append(_text(block))
            elif block.tag in ('ul', 'ol'):
                lines += [f'• {_text(item)}' for item in block if _LANG not in item.attrib]
    if lines:
        return '\n'.join(lines)
    summary = _untranslated(component, 'summary')
    return _text(summary) if summary is not None else None


def _developer(component: ET.Element) -> str | None:
    element = _untranslated(_untranslated(component, 'developer'), 'name')
    if element is None:
        element = _untranslated(component, 'developer_name')
    return _text(element) if element is not None else None


def _icon(share: Path, app_id: str) -> Path | None:
    """A vector icon if there is one, otherwise the largest bitmap."""
    hicolor = share / 'icons' / 'hicolor'
    vector = hicolor / 'scalable' / 'apps' / f'{app_id}.svg'
    if vector.is_file():
        return vector
    sized = [
        (int(match.group(1)), path)
        for path in hicolor.glob(f'*/apps/{app_id}.png')
        if (match := re.fullmatch(r'(\d+)x\d+', path.parent.parent.name))
    ]
    return max(sized, key=lambda item: item[0])[1] if sized else None


def read_app_details(app_id: str) -> AppDetails:
    for root in _INSTALL_ROOTS:
        share = root / app_id / 'current' / 'active' / 'export' / 'share'
        if not share.is_dir():
            continue
        return read_share_details(share, app_id)
    return AppDetails()


def read_share_details(share: Path, app_id: str) -> AppDetails:
    description = developer = None
    try:
        component = ET.parse(share / 'metainfo' / f'{app_id}.metainfo.xml').getroot()
    except (OSError, ET.ParseError):
        pass  # metainfo is optional; the icon can still be used
    else:
        description, developer = _description(component), _developer(component)
    return AppDetails(description, developer, _icon(share, app_id))
