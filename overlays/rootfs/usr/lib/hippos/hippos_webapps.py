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
WEBAPPS_DIR     = USERDATA / 'roms' / 'linuxapps'
WEBAPPS_LIST    = USERDATA / 'system' / 'webapps.json'
STATE_FILE      = USERDATA / 'system' / 'webapps-launchers.json'
WEBAPP_PROFILES = USERDATA / 'system' / 'webapps' / 'profiles'
WEBAPP_ICONS    = USERDATA / 'system' / 'webapps' / 'icons'
WEBAPPS_BIN     = Path('/usr/lib/hippos/hippos-webapps')
ADD_ICON        = Path('/usr/share/hippos/webapps/add-webapp.png')
ADD_WEBAPP_URL  = 'hippos:add'
ADD_WEBAPP_NAME = 'Add a web app'
DESKTOP_ENTRIES = USERDATA / '.local' / 'share' / 'applications'
DESKTOP_ENTRY_PREFIX = 'hippos-webapp-'
DESKTOP_FALLBACK_ICON = 'applications-internet'
MINT_PROFILES   = USERDATA / '.local' / 'share' / 'ice' / 'profiles'
MINT_CHROMIUM_BROWSERS = ('chromium', 'chromium-browser')
USER_AGENT      = 'Mozilla/5.0 (X11; Linux) HippOS-WebApps/1.0'
ICON_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.svg', '.ico', '.webp')


@dataclass
class WebApp:
    name: str
    url: str
    icon: str = ''
    description: str = ''


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


def chromium_command(chromium: str, url: str, profile: Path, *, kiosk: bool) -> list[str]:
    return [chromium, f'--app={url}', *(['--kiosk'] if kiosk else []), f'--user-data-dir={profile}',
            '--no-first-run', '--no-default-browser-check']


def sync() -> bool:
    apps = load_webapps()
    games = {ADD_WEBAPP_URL: ADD_WEBAPP_NAME, **{app.url: app.name for app in apps}}
    created, updated, removed = sync_launchers(WEBAPPS_DIR, STATE_FILE, '.webapp', games, 'Web App')
    details = {ADD_WEBAPP_URL: GameMetadata(ADD_WEBAPP_NAME, 'Add any website as a full-screen app.', None,
                                            ADD_ICON if ADD_ICON.exists() else None)}
    details |= {app.url: GameMetadata(app.name, app.description or app.url, None, Path(app.icon) if app.icon else None) for app in apps}
    changed = sync_gamelist(WEBAPPS_DIR, STATE_FILE, '.webapp', details)
    sync_desktop_entries(apps)
    if created or updated or removed or changed:
        reload_es()
    return bool(created or updated or removed or changed)


def _exec_arg(arg: str) -> str:
    arg = arg.replace('%', '%%')
    if not re.search(r'[\s"\'\\><~|&;$*?#()`]', arg):
        return arg
    return '"' + re.sub(r'(["`$\\])', r'\\\1', arg) + '"'


def _exec_line(args: list[str]) -> str:
    return ' '.join(_exec_arg(arg) for arg in args).replace('\\', '\\\\')


def _desktop_value(value: str) -> str:
    return ' '.join(value.split())


def desktop_entry(app: WebApp, profile: Path) -> str:
    return '\n'.join([
        '[Desktop Entry]',
        'Type=Application',
        f'Name={_desktop_value(app.name)}',
        f'Comment={_desktop_value(app.description or app.url)}',
        f'Exec={_exec_line(chromium_command("chromium", app.url, profile, kiosk=False))}',
        f'Icon={app.icon or DESKTOP_FALLBACK_ICON}',
        'Categories=Network;',
        'StartupNotify=true',
        'Actions=remove;',
        '',
        '[Desktop Action remove]',
        'Name=Remove web app',
        f'Exec={_exec_line([str(WEBAPPS_BIN), "remove", "--url", app.url])}',
        '',
    ])


def sync_desktop_entries(apps: list[WebApp]) -> None:
    DESKTOP_ENTRIES.mkdir(parents=True, exist_ok=True)
    wanted: dict[Path, str] = {}
    for app in apps:
        stem = _launcher_for(app.url).stem
        if not stem:
            continue
        entry_id = re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-') or 'webapp'
        wanted[DESKTOP_ENTRIES / f'{DESKTOP_ENTRY_PREFIX}{entry_id}.desktop'] = desktop_entry(app, WEBAPP_PROFILES / stem)
    for path in DESKTOP_ENTRIES.glob(f'{DESKTOP_ENTRY_PREFIX}*.desktop'):
        if path not in wanted:
            path.unlink()
    for path, content in wanted.items():
        if read_webapp(path) != content.strip():
            path.write_text(content, encoding='utf-8')


def ensure_chromium() -> None:
    if shutil.which('chromium'):
        return
    subprocess.run(['sudo', '-n', 'apt-get', 'install', '-y', '--no-install-recommends', 'chromium'], check=True)


class PageHead(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.manifest = ''
        self.icons: list[tuple[int, str]] = []
        self.descriptions: dict[str, str] = {}

    @property
    def description(self) -> str:
        return self.descriptions.get('description') or self.descriptions.get('og:description', '')

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or '' for key, value in attrs}
        if tag == 'meta':
            key = (values.get('name') or values.get('property', '')).lower()
            if key in ('description', 'og:description') and values.get('content', '').strip():
                self.descriptions.setdefault(key, ' '.join(values['content'].split()))
            return
        if tag != 'link':
            return
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


def read_page_head(page_url: str) -> PageHead | None:
    try:
        parser = PageHead()
        parser.feed(_fetch(page_url).decode('utf-8', errors='replace'))
    except (OSError, ValueError):
        return None
    return parser


def icon_candidates(page_url: str, parser: PageHead | None) -> list[str]:
    candidates: list[tuple[int, str]] = []
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


def fetch_icon(name: str, page_url: str, page: PageHead | None, icon_url: str = '') -> str:
    WEBAPP_ICONS.mkdir(parents=True, exist_ok=True)
    for url in ([icon_url] if icon_url else []) + icon_candidates(page_url, page):
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


def _reset_gamelist_entry(url: str) -> None:
    launcher = _launcher_for(url)
    gamelist = WEBAPPS_DIR / 'gamelist.xml'
    if not launcher.name or not gamelist.exists():
        return
    tree = ET.parse(gamelist)
    for game in tree.getroot().findall('game'):
        if game.findtext('path') != f'./{launcher.name}':
            continue
        image = game.find('image')
        if image is not None:
            (WEBAPPS_DIR / (image.text or '')).unlink(missing_ok=True)
        for field in (image, game.find('name'), game.find('desc')):
            if field is not None:
                game.remove(field)
        tree.write(gamelist, encoding='utf-8', xml_declaration=True)


def add(name: str, url: str, icon_url: str = '', description: str = '') -> WebApp:
    url = normalise_url(url)
    ensure_chromium()
    page = read_page_head(url)
    app = WebApp(name.strip() or urllib.parse.urlparse(url).hostname or url, url,
                 description=description.strip() or (page.description if page else ''))
    app.icon = fetch_icon(app.name, url, page, icon_url)
    _reset_gamelist_entry(url)
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


def _desktop_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    section = ''
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if line.startswith('['):
            section = line
        elif section == '[Desktop Entry]' and '=' in line:
            key, _, value = line.partition('=')
            fields.setdefault(key.strip(), value.strip())
    return fields


def import_mint_webapps() -> int:
    found = []
    for entry in sorted(DESKTOP_ENTRIES.glob('*.desktop')):
        if not entry.name.lower().startswith('webapp-'):
            continue
        fields = _desktop_fields(entry)
        if not fields.get('X-WebApp-URL'):
            continue
        url = normalise_url(fields['X-WebApp-URL'])
        app = WebApp(fields.get('Name') or urllib.parse.urlparse(url).hostname or url, url,
                     description=fields.get('Comment', ''))
        icon = Path(fields.get('Icon', ''))
        if icon.is_absolute() and icon.is_file():
            WEBAPP_ICONS.mkdir(parents=True, exist_ok=True)
            app.icon = str(WEBAPP_ICONS / f'{safe_filename(app.name, "webapp")}{icon.suffix.lower()}')
            shutil.copyfile(icon, app.icon)
        found.append((entry, entry.stem.split('-', 1)[1], fields, app))
    if not found:
        return 0
    known = {app.url for app in load_webapps()}
    save_webapps(load_webapps() + [app for *_, app in found if app.url not in known])
    sync()
    for entry, codename, fields, app in found:
        profile = MINT_PROFILES / codename
        target = WEBAPP_PROFILES / _launcher_for(app.url).stem
        if (fields.get('X-WebApp-Browser') in MINT_CHROMIUM_BROWSERS and profile.is_dir()
                and _launcher_for(app.url).stem and not target.exists()):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(profile, target)
        entry.unlink()
    return len(found)
