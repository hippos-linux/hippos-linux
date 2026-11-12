from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

from hippos_launcher_sync import GameMetadata, reload_es, safe_filename, sync_gamelist, sync_launchers

USERDATA        = Path('/userdata')
WEBAPPS_DIR     = USERDATA / 'roms' / 'webapps'
WEBAPPS_LIST    = USERDATA / 'system' / 'webapps.json'
STATE_FILE      = USERDATA / 'system' / 'webapps-launchers.json'
WEBAPP_PROFILES = USERDATA / 'system' / 'webapps' / 'profiles'
WEBAPP_ICONS    = USERDATA / 'system' / 'webapps' / 'icons'
WEBAPPS_BIN     = Path('/usr/lib/hippos/hippos-webapps')
ADD_ICON        = Path('/usr/share/hippos/webapps/add-webapp.png')
ADD_WEBAPP_URL  = 'hippos:add'
ADD_WEBAPP_NAME = 'Add a web app'
USER_AGENT      = 'Mozilla/5.0 (X11; Linux) HippOS-WebApps/1.0'
ICON_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.svg', '.ico', '.webp')


@dataclass
class WebApp:
    name: str
    url: str
    icon: str = ''


def read_webapp(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8').strip() or None
    except OSError:
        return None


def normalise_url(url: str) -> str:
    url = url.strip()
    return url if re.match(r'^[a-z][a-z0-9+.-]*://', url, re.I) else f'https://{url}'


def load_webapps() -> list[WebApp]:
    try:
        data = json.loads(WEBAPPS_LIST.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return []
    return [WebApp(**app) for app in data.get('apps', [])]


def save_webapps(apps: list[WebApp]) -> None:
    WEBAPPS_LIST.parent.mkdir(parents=True, exist_ok=True)
    temporary = WEBAPPS_LIST.with_suffix('.json.tmp')
    temporary.write_text(json.dumps({'apps': [asdict(app) for app in apps]}, indent=2) + '\n', encoding='utf-8')
    temporary.replace(WEBAPPS_LIST)


def sync() -> bool:
    apps = load_webapps()
    games = {ADD_WEBAPP_URL: ADD_WEBAPP_NAME, **{app.url: app.name for app in apps}}
    created, updated, removed = sync_launchers(WEBAPPS_DIR, STATE_FILE, '.webapp', games, 'Web App')
    details = {ADD_WEBAPP_URL: GameMetadata(ADD_WEBAPP_NAME, 'Add any website as a full-screen app.', None,
                                            ADD_ICON if ADD_ICON.exists() else None)}
    details |= {app.url: GameMetadata(app.name, app.url, None, Path(app.icon) if app.icon else None) for app in apps}
    changed = sync_gamelist(WEBAPPS_DIR, STATE_FILE, '.webapp', details)
    if created or updated or removed or changed:
        reload_es()
    return bool(created or updated or removed or changed)


def ensure_chromium() -> None:
    if shutil.which('chromium'):
        return
    subprocess.run(['sudo', '-n', 'apt-get', 'install', '-y', '--no-install-recommends', 'chromium'], check=True)


class _IconLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.manifest = ''
        self.icons: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != 'link':
            return
        values = {key: value or '' for key, value in attrs}
        rel = values.get('rel', '').lower().split()
        href = values.get('href', '')
        if not href:
            return
        if 'manifest' in rel:
            self.manifest = href
        elif 'apple-touch-icon' in rel or 'icon' in rel:
            self.icons.append((_icon_size(values.get('sizes', '')) + ('apple-touch-icon' in rel), href))


def _icon_size(sizes: str) -> int:
    found = [int(width) for width, _ in re.findall(r'(\d+)x(\d+)', sizes)]
    return max(found, default=0)


def _fetch(url: str, limit: int = 4_000_000) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read(limit)


def icon_candidates(page_url: str) -> list[str]:
    candidates: list[tuple[int, str]] = []
    try:
        parser = _IconLinks()
        parser.feed(_fetch(page_url).decode('utf-8', errors='replace'))
    except (OSError, ValueError):
        parser = None
    if parser and parser.manifest:
        manifest_url = urllib.parse.urljoin(page_url, parser.manifest)
        try:
            manifest = json.loads(_fetch(manifest_url))
            candidates += [(_icon_size(icon.get('sizes', '')), urllib.parse.urljoin(manifest_url, icon['src']))
                           for icon in manifest.get('icons', []) if icon.get('src')]
        except (OSError, ValueError, AttributeError):
            pass
    if parser:
        candidates += [(size, urllib.parse.urljoin(page_url, href)) for size, href in parser.icons]
    candidates.append((0, urllib.parse.urljoin(page_url, '/favicon.ico')))
    return [url for _, url in sorted(candidates, key=lambda item: -item[0])]


def fetch_icon(name: str, page_url: str, icon_url: str = '') -> str:
    WEBAPP_ICONS.mkdir(parents=True, exist_ok=True)
    for url in ([icon_url] if icon_url else []) + icon_candidates(page_url):
        try:
            data = _fetch(url)
        except (OSError, ValueError):
            continue
        suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if not data or suffix not in ICON_EXTENSIONS:
            suffix = '.svg' if data.lstrip().startswith(b'<') else '.png'
        target = WEBAPP_ICONS / f'{safe_filename(name, "webapp")}{suffix}'
        target.write_bytes(data)
        return str(target)
    return ''


def _launcher_for(url: str) -> Path:
    try:
        return Path(json.loads(STATE_FILE.read_text(encoding='utf-8')).get(url, ''))
    except (OSError, json.JSONDecodeError):
        return Path()


def _drop_gamelist_image(url: str) -> None:
    launcher = _launcher_for(url)
    gamelist = WEBAPPS_DIR / 'gamelist.xml'
    if not launcher.name or not gamelist.exists():
        return
    tree = ET.parse(gamelist)
    for game in tree.getroot().findall('game'):
        image = game.find('image')
        if game.findtext('path') == f'./{launcher.name}' and image is not None:
            (WEBAPPS_DIR / (image.text or '')).unlink(missing_ok=True)
            game.remove(image)
            tree.write(gamelist, encoding='utf-8', xml_declaration=True)


def add(name: str, url: str, icon_url: str = '') -> WebApp:
    url = normalise_url(url)
    ensure_chromium()
    app = WebApp(name.strip() or urllib.parse.urlparse(url).hostname or url, url)
    app.icon = fetch_icon(app.name, url, icon_url)
    _drop_gamelist_image(url)
    save_webapps([existing for existing in load_webapps() if existing.url != url] + [app])
    sync()
    return app


def remove(url: str) -> bool:
    url = normalise_url(url)
    apps = load_webapps()
    gone = [app for app in apps if app.url == url]
    if not gone:
        return False
    launcher = _launcher_for(url)
    save_webapps([app for app in apps if app.url != url])
    sync()
    for app in gone:
        if app.icon:
            Path(app.icon).unlink(missing_ok=True)
    if launcher.name:
        shutil.rmtree(WEBAPP_PROFILES / launcher.stem, ignore_errors=True)
    return True
