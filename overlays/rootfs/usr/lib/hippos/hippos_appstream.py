from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_INSTALL_ROOTS = (Path('/userdata/.local/share/flatpak/app'), Path('/var/lib/flatpak/app'))
_LANG = '{http://www.w3.org/XML/1998/namespace}lang'
_METAINFO_DIRS = (Path('/usr/share/metainfo'), Path('/usr/share/appdata'))
SCREENSHOT_MAX_WIDTH = 1280

@dataclass(frozen=True)
class AppDetails:
    description: str | None = None
    developer: str | None = None
    icon: Path | None = None
    screenshot: str | None = None

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

def hicolor_icon(share: Path, app_id: str) -> Path | None:
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
        pass
    else:
        description, developer = _description(component), _developer(component)
    return AppDetails(description, developer, hicolor_icon(share, app_id))

def _default_screenshot(component: ET.Element) -> str | None:
    screenshots = component.find('screenshots')
    if screenshots is None:
        return None
    shot = next((s for s in screenshots.findall('screenshot') if s.get('type') == 'default'),
                screenshots.find('screenshot'))
    if shot is None:
        return None
    images = [(int(image.get('width') or 0), image.get('type'), (image.text or '').strip())
              for image in shot.findall('image') if _LANG not in image.attrib and (image.text or '').strip()]
    fitting = [image for image in images if image[1] == 'thumbnail' and image[0] <= SCREENSHOT_MAX_WIDTH]
    chosen = max(fitting) if fitting else next((image for image in images if image[1] == 'source'), None)
    return chosen[2] if chosen else None

def _catalog_component(component_id: str, package: str) -> ET.Element | None:
    try:
        dump = subprocess.run(['appstreamcli', 'dump', component_id], capture_output=True, text=True, timeout=30)
        component = ET.fromstring(dump.stdout) if dump.returncode == 0 and dump.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired, ET.ParseError):
        return None
    if component is None or component.findtext('pkgname') != package:
        return None
    return component

def read_package_details(package: str, files: list[Path], desktop: Path) -> AppDetails:
    component_ids = []
    for path in files:
        if path.parent in _METAINFO_DIRS and path.suffix == '.xml':
            try:
                component_ids.append(ET.parse(path).getroot().findtext('id') or '')
            except (OSError, ET.ParseError):
                pass
    component_ids += [desktop.name, desktop.stem]
    for component_id in filter(None, component_ids):
        component = _catalog_component(component_id, package)
        if component is not None:
            return AppDetails(_description(component), _developer(component), None, _default_screenshot(component))
    return AppDetails()
