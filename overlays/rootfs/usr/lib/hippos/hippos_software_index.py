from __future__ import annotations

import gzip
import hashlib
import json
import locale
import os
import platform
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

import hippos_flatpak_apps
import hippos_store_catalog
from hippos_apt import missing_packages, recorded_user_packages
from hippos_store_search import APT_PREFIX, FLATPAK_PREFIX, debian_results, refresh_apt_lists

FLATHUB_APPSTREAM = Path.home() / '.local/share/flatpak/appstream/flathub' / platform.machine() / 'active'
DEP11_DIR = Path('/var/lib/swcatalog/yaml')
DEP11_ICONS = Path('/var/lib/swcatalog/icons')
INDEX_DIR = Path(hippos_store_catalog.CACHE_DIR) / 'software'
INDEX_FILE = INDEX_DIR / 'index.json'
DETAILS_FILE = INDEX_DIR / 'details.jsonl'
INDEX_MAX_AGE_S = 24 * 3600
INDEX_VERSION = 8
ODRS_URL = 'https://odrs.gnome.org/1.0/reviews/api'
FLATHUB_POPULAR_URL = 'https://flathub.org/api/v2/collection/popular?per_page=250&page='
POPCON_URL = 'https://popcon.debian.org/by_inst.gz'
RATING_PRIOR_COUNT = 10
RATING_PRIOR = 60
DEBIAN_SCREENSHOTS_URL = 'https://screenshots.debian.net/json/package/'
USER_AGENT = 'hippos-software/1.0'
RECOMP_CREDIT = 'Listed in the RecompLauncher catalogue (recomplauncher.com).'
UPGRADE = '/usr/lib/hippos/hippos-upgrade'
SYSTEM_UPDATE_RUN_ORDER = ('patch', 'emulators', 'emulator', 'frontend', 'kernel', 'system')
SYSTEM_UPDATE_LABELS = {'system': 'HippOS', 'kernel': 'Kernel', 'frontend': 'EmulationStation', 'emulators': 'Emulators'}
XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'
APP_TYPES = {'desktop', 'desktop-application'}
CATALOG_CATEGORIES = {'apps': 'HippOS picks', 'webapps': 'HippOS picks', 'ports': 'Ports'}

SOURCE_LABELS = {'hippos': 'HippOS', 'flatpak': 'Flathub', 'debian': 'Debian', 'recomp': 'Recomp'}

CATEGORIES = (
    ('HippOS picks', ()),
    ('Games', ('Game',)),
    ('Internet', ('Network',)),
    ('Multimedia', ('AudioVideo', 'Audio', 'Video')),
    ('Graphics', ('Graphics',)),
    ('Office', ('Office',)),
    ('Development', ('Development',)),
    ('Education', ('Education',)),
    ('Science', ('Science',)),
    ('System', ('System', 'Settings')),
    ('Utilities', ('Utility',)),
    ('Ports', ()),
    ('Recomps', ()),
)


@dataclass
class Source:
    kind: str
    name: str
    version: str = ''
    flatpak_id: str = ''

    @property
    def label(self) -> str:
        return SOURCE_LABELS[self.kind]


@dataclass
class App:
    key: str
    name: str
    summary: str
    icon: str = ''
    categories: list[str] = field(default_factory=list)
    released: int = 0
    desktop_id: str = ''
    sources: list[Source] = field(default_factory=list)
    details_offset: int = -1
    component_ids: list[str] = field(default_factory=list)
    rating: int = 0
    ratings: int = 0
    rating_id: str = ''
    installs: int = 0
    installs_source: str = ''
    aliases: list[str] = field(default_factory=list)

    def source(self, kind: str) -> Source | None:
        return next((source for source in self.sources if source.kind == kind), None)

    def matches(self, words: list[str]) -> bool:
        text = f'{self.name} {self.summary} {self.key}'.lower()
        return all(word in text for word in words)


@dataclass
class Details:
    description: str = ''
    developer: str = ''
    license: str = ''
    homepage: str = ''
    screenshot: str = ''


@dataclass
class SystemUpdate:
    kind: str
    name: str
    installed: str
    available: str
    command: list[str]
    needs_restart: bool
    detail: str = ''

    @property
    def key(self) -> str:
        return f'system:{self.kind}:{self.name}'

    @property
    def title(self) -> str:
        return SYSTEM_UPDATE_LABELS.get(self.kind, self.name)

    @property
    def change(self) -> str:
        if self.kind in ('patch', 'emulators'):
            return self.detail
        if self.installed == self.available:
            return f'{self.available}, rebuilt'
        return f"{self.installed or 'not installed'} → {self.available}"


@dataclass
class Review:
    rating: int
    summary: str
    description: str
    author: str
    date: int


def _merge_key(component_id: str) -> str:
    return component_id.removesuffix('.desktop').lower()


def _main_categories(categories: list[str]) -> list[str]:
    return [name for name, members in CATEGORIES if set(members) & set(categories)]


def _plain(element: ET.Element | None) -> str:
    if element is None:
        return ''
    paragraphs = []
    for child in element:
        if child.get(XML_LANG):
            continue
        if child.tag == 'p':
            paragraphs.append(' '.join(''.join(child.itertext()).split()))
        elif child.tag in ('ul', 'ol'):
            paragraphs.extend('• ' + ' '.join(''.join(item.itertext()).split())
                              for item in child if item.tag == 'li' and not item.get(XML_LANG))
    return '\n\n'.join(paragraph for paragraph in paragraphs if paragraph)


def _untranslated(element: ET.Element, tag: str) -> str:
    return next((child.text or '' for child in element.findall(tag) if not child.get(XML_LANG)), '').strip()


def read_flathub(appstream_dir: Path = FLATHUB_APPSTREAM):
    xml_path = appstream_dir / 'appstream.xml'
    if not xml_path.exists():
        xml_path = appstream_dir / 'appstream.xml.gz'
    if not xml_path.exists():
        return
    stream = gzip.open(xml_path) if xml_path.suffix == '.gz' else open(xml_path, 'rb')
    with stream:
        for _, element in ET.iterparse(stream):
            if element.tag != 'component':
                continue
            if element.get('type') in APP_TYPES and (app_id := element.findtext('id')):
                icon = next((node.text for node in element.findall('icon')
                             if node.get('type') == 'cached' and node.get('height') == '128'), '') or ''
                icon_path = appstream_dir / 'icons' / '128x128' / icon if icon else None
                screenshot = next((image.text for shot in element.iter('screenshot') if shot.get('type') == 'default'
                                   for image in shot.findall('image') if image.get('type') == 'source'), '') or ''
                timestamps = [int(release.get('timestamp', 0) or 0) for release in element.iter('release')]
                developer_node = element.find('developer')
                developer = (_untranslated(element, 'developer_name')
                             or (_untranslated(developer_node, 'name') if developer_node is not None else ''))
                homepage = next((url.text or '' for url in element.findall('url') if url.get('type') == 'homepage'), '')
                version = next((release.get('version', '') for release in element.iter('release')), '')
                app = App(
                    key=_merge_key(app_id),
                    name=_untranslated(element, 'name') or app_id,
                    summary=_untranslated(element, 'summary'),
                    icon=str(icon_path) if icon_path and icon_path.exists() else '',
                    categories=_main_categories([node.text or '' for node in element.iter('category')]),
                    released=max(timestamps, default=0),
                    sources=[Source('flatpak', f'{FLATPAK_PREFIX}{app_id}', version, app_id)],
                    component_ids=[app_id],
                )
                details = Details(_plain(element.find('description')), developer,
                                  element.findtext('project_license') or '', homepage, screenshot)
                yield app, details
            element.clear()


def _c(value) -> str:
    if isinstance(value, dict):
        return str(value.get('C') or value.get('en') or '')
    return str(value or '')


def _html_text(html: str) -> str:
    try:
        return _plain(ET.fromstring(f'<description>{html}</description>'))
    except ET.ParseError:
        return ' '.join(re.sub(r'<[^>]+>', ' ', html).split())


def read_dep11(yaml_dir: Path = DEP11_DIR, icons_dir: Path = DEP11_ICONS):
    arch = hippos_store_catalog.DEB_ARCH
    for path in sorted(yaml_dir.glob(f'*_dep11_Components-{arch}.yml.gz')):
        with gzip.open(path) as stream:
            documents = yaml.load_all(stream, Loader=yaml.CSafeLoader)
            header = next(documents, None) or {}
            origin, media = header.get('Origin', ''), header.get('MediaBaseUrl', '')
            for component in documents:
                package = component.get('Package', '')
                if component.get('Type') not in APP_TYPES or not package:
                    continue
                cached_icons = sorted((component.get('Icon') or {}).get('cached', []),
                                      key=lambda cached: cached.get('height', 0), reverse=True)
                icon_path = next((path for cached in cached_icons if cached.get('height') in (128, 64)
                                  for path in [icons_dir / origin / f"{cached['height']}x{cached['height']}"
                                               / cached['name']] if path.exists()), None)
                shot = next((item for item in component.get('Screenshots') or [] if item.get('default')), None)
                screenshot = f"{media}/{shot['source-image']['url']}" if shot and shot.get('source-image') else ''
                releases = component.get('Releases') or []
                developer = _c(component.get('DeveloperName')) or _c((component.get('Developer') or {}).get('name'))
                app = App(
                    key=_merge_key(component.get('ID', package)),
                    name=_c(component.get('Name')) or package,
                    summary=_c(component.get('Summary')),
                    icon=str(icon_path) if icon_path else '',
                    categories=_main_categories(component.get('Categories') or []),
                    released=max((int(release.get('unix-timestamp', 0) or 0) for release in releases), default=0),
                    desktop_id=next(iter((component.get('Launchable') or {}).get('desktop-id') or []), ''),
                    sources=[Source('debian', f'{APT_PREFIX}{package}', str(releases[0].get('version', ''))
                                    if releases else '')],
                    component_ids=[component.get('ID', package)],
                )
                details = Details(_html_text(_c(component.get('Description'))), developer,
                                  str(component.get('ProjectLicense') or ''),
                                  str((component.get('Url') or {}).get('homepage') or ''), screenshot)
                yield app, details


def read_catalog(packages: list[dict]):
    for package in packages:
        category = CATALOG_CATEGORIES.get(package.get('category', ''))
        if category is None or not hippos_store_catalog.for_this_machine(package):
            continue
        flatpak_id = package.get('flatpak_id', '') if package.get('type') == 'flatpak' else ''
        packages = package.get('apt_packages', []) if package.get('type') in ('apt', 'deb') else []
        app = App(
            key=_merge_key(flatpak_id) if flatpak_id else f"hippos:{package['id']}",
            name=package.get('name', package['id']),
            summary=package.get('description', '').split('. ')[0],
            icon=package.get('icon_url', ''),
            categories=[category],
            sources=[Source('hippos', package['id'], package.get('version', ''), flatpak_id)],
            component_ids=[flatpak_id] if flatpak_id else [],
            aliases=[_merge_key(i) for i in package.get('appstream_ids', [])] + [f'{APT_PREFIX}{p}' for p in packages],
        )
        yield app, Details(package.get('description', ''), package.get('packager', 'HippOS'), '',
                           package.get('url', ''), package.get('preview_url', ''))


def read_recomps(entries: list[dict]):
    for entry in entries:
        if not entry.get('id') or hippos_store_catalog.recomp_linux_pattern(entry) is None:
            continue
        released = entry.get('released_at') or ''
        app = App(
            key=f"recomp:{entry['id']}",
            name=entry.get('name') or entry['id'],
            summary=entry.get('blurb') or entry.get('game') or '',
            icon=entry.get('icon') or '',
            categories=['Recomps', 'Games'],
            released=int(time.mktime(time.strptime(released[:19], '%Y-%m-%dT%H:%M:%S'))) if released else 0,
            sources=[Source('recomp', f"{hippos_store_catalog.RECOMP_PREFIX}{entry['id']}", entry.get('version', ''))],
            installs=int(entry.get('downloads') or 0),
            installs_source='recomp' if entry.get('downloads') else '',
        )
        needs = entry.get('needs') or ''
        description = '\n\n'.join(part for part in (entry.get('blurb'), entry.get('description'),
                                                     f'Needs: {needs}' if needs else '', RECOMP_CREDIT) if part)
        yield app, Details(description, entry.get('author') or '', entry.get('license') or '',
                           f"https://github.com/{entry['repo']}", entry.get('hero') or entry.get('cover') or '')


def _combine(existing: App, app: App) -> None:
    known = {source.name for source in existing.sources}
    existing.sources = sorted(existing.sources + [s for s in app.sources if s.name not in known],
                              key=lambda source: list(SOURCE_LABELS).index(source.kind))
    existing.categories = existing.categories + [c for c in app.categories if c not in existing.categories]
    existing.icon = existing.icon or app.icon
    existing.component_ids += [i for i in app.component_ids if i not in existing.component_ids]
    existing.desktop_id = existing.desktop_id or app.desktop_id
    existing.released = max(existing.released, app.released)


def _merge(apps: dict[str, App], app: App) -> App:
    existing = apps.get(app.key)
    if existing is None:
        apps[app.key] = app
        return app
    _combine(existing, app)
    if app.sources[0].kind == 'hippos':
        existing.name, existing.summary = app.name, app.summary or existing.summary
    return existing


def _absorb_aliases(apps: dict[str, App], details_kind: dict[str, str]) -> None:
    owner_of_package = {source.name: app.key for app in apps.values() for source in app.sources
                        if source.kind == 'debian'}
    for owner in [app for app in apps.values() if app.aliases]:
        for alias in owner.aliases:
            key = owner_of_package.get(alias, alias)
            target = apps.get(key)
            if target is None or target is owner:
                continue
            del apps[key]
            _combine(owner, target)
            for source in target.sources:
                owner_of_package[source.name] = owner.key
            if details_kind.get(owner.key) == 'hippos' and details_kind.get(key) not in (None, 'hippos'):
                owner.details_offset, details_kind[owner.key] = target.details_offset, details_kind[key]


def _get_json(url: str, timeout: int = 20, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={'User-Agent': USER_AGENT,
                                                             'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def fetch_ratings() -> dict:
    try:
        return _get_json(f'{ODRS_URL}/ratings', timeout=30)
    except (OSError, ValueError):
        return {}


def apply_ratings(apps: list[App], ratings: dict) -> None:
    by_id: dict[str, str] = {}
    for rating_id, stars in ratings.items():
        if isinstance(stars, dict):
            lowered = rating_id.lower()
            if lowered not in by_id or stars.get('total', 0) > ratings[by_id[lowered]].get('total', 0):
                by_id[lowered] = rating_id
    for app in apps:
        candidates = [i for component_id in app.component_ids for i in (component_id, f'{component_id}.desktop')]
        if app.desktop_id:
            candidates.append(app.desktop_id)
        known = [(ratings[by_id[i.lower()]].get('total', 0), by_id[i.lower()]) for i in candidates
                 if i.lower() in by_id]
        if not known:
            continue
        total, rating_id = max(known)
        stars = ratings[rating_id]
        if total:
            app.rating = round(sum(star * stars.get(f'star{star}', 0) for star in range(1, 6)) * 20 / total)
            app.ratings, app.rating_id = total, rating_id


def fetch_flathub_installs() -> dict[str, int]:
    installs: dict[str, int] = {}
    page, pages = 1, 1
    while page <= pages:
        try:
            listing = _get_json(f'{FLATHUB_POPULAR_URL}{page}', timeout=30)
        except (OSError, ValueError):
            break
        pages = int(listing.get('totalPages', 0) or 0)
        for hit in listing.get('hits', []):
            if hit.get('app_id'):
                installs[hit['app_id']] = int(hit.get('installs_last_month', 0) or 0)
        page += 1
    return installs


def fetch_popcon() -> dict[str, int]:
    request = urllib.request.Request(POPCON_URL, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = gzip.decompress(response.read()).decode('utf-8', errors='replace')
    except (OSError, ValueError, EOFError):
        return {}
    installs = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 3 and not line.startswith('#') and fields[2].isdigit():
            installs[fields[1]] = int(fields[2])
    return installs


def apply_installs(apps: list[App], flathub: dict[str, int], popcon: dict[str, int]) -> None:
    for app in apps:
        counts = [(app.installs, app.installs_source)] if app.installs else []
        for source in app.sources:
            if source.flatpak_id in flathub:
                counts.append((flathub[source.flatpak_id], 'flatpak'))
            if source.kind == 'debian' and source.name[len(APT_PREFIX):] in popcon:
                counts.append((popcon[source.name[len(APT_PREFIX):]], 'debian'))
        if counts:
            app.installs, app.installs_source = max(counts)


def build(index_file: Path = INDEX_FILE, details_file: Path = DETAILS_FILE, readers=None,
          ratings: dict | None = None, flathub_installs: dict[str, int] | None = None,
          popcon: dict[str, int] | None = None) -> list[App]:
    if readers is None:
        readers = (read_catalog(hippos_store_catalog.load_catalog()), read_flathub(),
                   read_dep11(), read_recomps(hippos_store_catalog.load_recomp_catalog()))
        ratings, flathub_installs, popcon = fetch_ratings(), fetch_flathub_installs(), fetch_popcon()
    index_file.parent.mkdir(parents=True, exist_ok=True)
    apps: dict[str, App] = {}
    details_kind: dict[str, str] = {}
    temporary_details = details_file.with_suffix('.tmp')
    with open(temporary_details, 'w', encoding='utf-8') as details_out:
        for reader in readers:
            for app, details in reader:
                merged = _merge(apps, app)
                if details_kind.get(app.key) in (None, 'hippos'):
                    details_kind[app.key] = app.sources[0].kind
                    merged.details_offset = details_out.tell()
                    details_out.write(json.dumps(asdict(details)) + '\n')
    os.replace(temporary_details, details_file)
    _absorb_aliases(apps, details_kind)
    ordered = sorted(apps.values(), key=lambda app: app.name.lower())
    apply_ratings(ordered, ratings or {})
    apply_installs(ordered, flathub_installs or {}, popcon or {})
    temporary_index = index_file.with_suffix('.tmp')
    temporary_index.write_text(json.dumps({'version': INDEX_VERSION, 'apps': [asdict(app) for app in ordered]}),
                               encoding='utf-8')
    os.replace(temporary_index, index_file)
    return ordered


def _from_dict(data: dict) -> App:
    return App(**{**data, 'sources': [Source(**source) for source in data['sources']]})


def load(index_file: Path = INDEX_FILE) -> list[App] | None:
    try:
        data = json.loads(index_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if data.get('version') != INDEX_VERSION:
        return None
    return [_from_dict(app) for app in data['apps']]


def stale(index_file: Path = INDEX_FILE) -> bool:
    try:
        return time.time() - index_file.stat().st_mtime > INDEX_MAX_AGE_S
    except FileNotFoundError:
        return True


def refresh_sources() -> None:
    hippos_flatpak_apps.refresh_appstream()
    refresh_apt_lists()


def apt_details(package: str) -> Details:
    listing = subprocess.run(['apt-cache', 'show', '--no-all-versions', package],
                             capture_output=True, text=True, check=False).stdout
    fields: dict[str, list[str]] = {}
    current = ''
    for line in listing.splitlines():
        if line.startswith((' ', '\t')) and current:
            fields[current].append(line[1:])
        elif ':' in line:
            current, _, value = line.partition(':')
            fields[current] = [value.strip()]
    description = fields.get('Description-en') or fields.get('Description') or ['']
    body = '\n'.join('' if line.strip() == '.' else line for line in description[1:]).strip()
    return Details(body or description[0], fields.get('Maintainer', [''])[0], '', fields.get('Homepage', [''])[0])


def package_apps(term: str, apps: list[App]) -> tuple[list[App], set[str]]:
    known = {source.name for app in apps for source in app.sources}
    results = [result for result in debian_results(term) if result.name not in known]
    return ([App(key=f'apt:{result.name[len(APT_PREFIX):]}', name=result.title, summary=result.description,
                 sources=[Source('debian', result.name, result.version)]) for result in results],
            {result.name for result in results if result.installed})


def debian_screenshot(package: str) -> str:
    try:
        shots = _get_json(DEBIAN_SCREENSHOTS_URL + package).get('screenshots', [])
    except (OSError, ValueError, AttributeError):
        return ''
    return shots[0].get('screenshot_image_url', '') if shots else ''


def _user_hash() -> str:
    try:
        machine = Path('/etc/machine-id').read_text(encoding='utf-8').strip()
    except OSError:
        machine = ''
    return hashlib.sha1(f'{machine}:{os.environ.get("USER", "")}'.encode()).hexdigest()


def fetch_reviews(app: App, limit: int = 5) -> list[Review]:
    if not app.rating_id:
        return []
    body = {'user_hash': _user_hash(), 'app_id': app.rating_id, 'locale': locale.getlocale()[0] or 'en_GB',
            'distro': 'Debian', 'version': next((s.version for s in app.sources if s.version), 'latest'),
            'limit': limit}
    try:
        found = _get_json(f'{ODRS_URL}/fetch', body=body)
    except (OSError, ValueError):
        return []
    return [Review(int(review.get('rating', 0) or 0), str(review.get('summary') or ''),
                   str(review.get('description') or ''), str(review.get('user_display') or 'Anonymous'),
                   int(review.get('date_created', 0) or 0))
            for review in found if isinstance(review, dict)][:limit]


def details(app: App, details_file: Path = DETAILS_FILE) -> Details:
    if app.details_offset < 0:
        debian = app.source('debian')
        return apt_details(debian.name[len(APT_PREFIX):]) if debian else Details()
    try:
        with open(details_file, encoding='utf-8') as stream:
            stream.seek(app.details_offset)
            return Details(**json.loads(stream.readline()))
    except (OSError, ValueError):
        return Details()


def installed_names(apps: list[App]) -> set[str]:
    names = {f'{FLATPAK_PREFIX}{app_id}' for app_id in hippos_flatpak_apps.installed_app_ids()}
    packages = [source.name[len(APT_PREFIX):] for app in apps for source in app.sources if source.kind == 'debian']
    if packages:
        missing = set(missing_packages(packages))
        names |= {f'{APT_PREFIX}{package}' for package in packages if package not in missing}
    names |= set(hippos_store_catalog.load_state())
    installed_keys = {name[len(FLATPAK_PREFIX):].lower() for name in names if name.startswith(FLATPAK_PREFIX)}
    names |= {source.name for app in apps if app.key in installed_keys
              for source in app.sources if source.kind == 'hippos'}
    return names


def catalog_updates(catalog: list[dict], state: dict) -> set[str]:
    return {package['id'] for package in catalog
            if package['id'] in state and package.get('version', 'latest') not in ('', 'latest')
            and state[package['id']].get('version') != package['version']}


def system_updates() -> list[SystemUpdate]:
    listing = subprocess.run([UPGRADE, 'list-available'], capture_output=True, text=True, check=False).stdout
    try:
        found = json.loads(listing)
    except ValueError:
        return []
    updates = [SystemUpdate(str(u.get('kind', '')), str(u.get('name', '')), str(u.get('installed') or ''),
                            str(u.get('available') or ''), [str(part) for part in u.get('command', [])],
                            bool(u.get('needs_restart')), str(u.get('detail') or ''))
               for u in found if isinstance(u, dict) and u.get('command')]
    emulators = [update for update in updates if update.kind == 'emulator']
    if len(emulators) > 1:
        updates = [update for update in updates if update.kind != 'emulator']
        updates.append(SystemUpdate('emulators', 'emulators', '', '', ['update-all-emulators'], False,
                                    f'{len(emulators)} updates'))
    return sorted(updates, key=lambda u: (-run_position(u), u.name.lower()))


def run_position(update: SystemUpdate) -> int:
    return SYSTEM_UPDATE_RUN_ORDER.index(update.kind) if update.kind in SYSTEM_UPDATE_RUN_ORDER else -1


def recomp_updates(entries: list[dict], state: dict) -> set[str]:
    prefix = hippos_store_catalog.RECOMP_PREFIX
    latest = {f"{prefix}{entry['id']}": str(entry.get('version') or '') for entry in entries if entry.get('id')}
    return {name for name, installed in state.items() if name in latest and latest[name]
            and str(installed.get('version', '')).lstrip('vV') != latest[name].lstrip('vV')}


def updatable_names() -> set[str]:
    names = {f'{FLATPAK_PREFIX}{app_id}' for app_id in hippos_flatpak_apps.updates_available()}
    state = hippos_store_catalog.load_state()
    names |= catalog_updates(hippos_store_catalog.load_catalog(), state)
    names |= recomp_updates(hippos_store_catalog.load_recomp_catalog(), state)
    user_packages = set(recorded_user_packages())
    listing = subprocess.run(['apt', 'list', '--upgradable'], capture_output=True, text=True, check=False).stdout
    for line in listing.splitlines():
        package = line.split('/', 1)[0]
        if package in user_packages:
            names.add(f'{APT_PREFIX}{package}')
    return names


def in_category(apps: list[App], category: str) -> list[App]:
    return [app for app in apps if category in app.categories]


def search(apps: list[App], term: str) -> list[App]:
    words = term.lower().split()
    if not words:
        return []
    found = [app for app in apps if app.matches(words)]
    return sorted(found, key=lambda app: (not app.name.lower().startswith(words[0]), app.name.lower()))


SORTS = {
    'Most installed': lambda app: (-app.installs, app.name.lower()),
    'Top rated': lambda app: (-(app.rating * app.ratings + RATING_PRIOR * RATING_PRIOR_COUNT)
                              / (app.ratings + RATING_PRIOR_COUNT), app.name.lower()),
    'Name': lambda app: app.name.lower(),
    'Recently updated': lambda app: (-app.released, app.name.lower()),
}


def sort_apps(apps: list[App], order: str) -> list[App]:
    return sorted(apps, key=SORTS[order])


def main() -> None:
    refresh_sources()
    build()


if __name__ == '__main__':
    main()
