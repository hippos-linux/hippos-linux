from __future__ import annotations

import os
import re
import shlex
import shutil
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from hippos_appstream import read_package_details
from hippos_apt import owning_package, package_files
from hippos_desktop_entries import DesktopApp, find_icon, read_desktop_file
from hippos_launcher_sync import GameMetadata, launchers_with, reload_es, update_gamelist

_APPLICATIONS = Path('/usr/share/applications')
_SYSTEM_PATH = '/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games'

LINUX_GAMES_DIR = Path('/userdata/roms/linux')
CLAIMS = Path('/userdata/system/linux-games-apt-claims')
LAUNCHER_EXTENSION = '.sh'
APT_MARKER = 'hippos-linux-games-apt'
USER_AGENT = 'HippOS-LinuxGames/1.0'

_LAUNCHER_TEMPLATE = """\
#!/bin/bash
# HippOS Linux game: {name}
{marker}export HOME=/userdata
export XDG_CONFIG_HOME=/userdata/system/.config
export XDG_DATA_HOME=/userdata/system/.local/share
exec {command}
"""

def launcher_path(name: str) -> Path:
    slug = re.sub(r'[^A-Za-z0-9._ -]', '', name).strip().replace(' ', '_')
    return LINUX_GAMES_DIR / f'{slug or "game"}{LAUNCHER_EXTENSION}'

def catalog_launcher(pkg_id: str) -> Path:
    return LINUX_GAMES_DIR / f'{pkg_id}{LAUNCHER_EXTENSION}'

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

def _download(url: str, folder: Path) -> Path | None:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower() or '.png'
    target = folder / f'art{suffix}'
    try:
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:
            target.write_bytes(response.read())
    except (OSError, ValueError):
        return None
    return target

def update_details(games: dict[Path, tuple[GameMetadata, str | None]]) -> bool:
    has_image = launchers_with(LINUX_GAMES_DIR, 'image')
    with tempfile.TemporaryDirectory() as scratch:
        details = {}
        for launcher, (metadata, image_url) in games.items():
            if image_url and launcher.resolve() not in has_image:
                folder = Path(scratch) / launcher.stem
                folder.mkdir()
                metadata = GameMetadata(metadata.name, metadata.description, metadata.developer,
                                        _download(image_url, folder) or metadata.image)
            details[launcher] = metadata
        return update_gamelist(LINUX_GAMES_DIR, LAUNCHER_EXTENSION, details)

def desktop_game_details(app: DesktopApp) -> GameMetadata:
    return GameMetadata(app.name, app.comment, None, find_icon(app.icon))

def apt_game_details(package: str, desktop: Path, app: DesktopApp) -> tuple[GameMetadata, str | None]:
    appstream = read_package_details(package, package_files(package), desktop)
    fallback = desktop_game_details(app)
    return (GameMetadata(app.name, appstream.description or fallback.description, appstream.developer, fallback.image),
            appstream.screenshot)

def launcher_command(launcher: Path) -> str | None:
    try:
        lines = launcher.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    return next((line[len('exec '):] for line in reversed(lines) if line.startswith('exec ')), None)

def packaged_game_details(launcher: Path) -> tuple[GameMetadata, str | None] | None:
    command = launcher_command(launcher)
    try:
        binary = shutil.which(shlex.split(command)[0], path=_SYSTEM_PATH) if command else None
    except ValueError:
        binary = None
    package = owning_package(Path(binary).resolve()) if binary else None
    if package is None:
        return None
    for desktop in package_files(package):
        if desktop.parent == _APPLICATIONS and desktop.suffix == '.desktop' and (app := read_desktop_file(desktop)):
            return apt_game_details(package, desktop, app)
    return None

def add_catalog_game(pkg: dict) -> Path:
    name = pkg.get('name', pkg['id'])
    command = ' '.join([pkg['launcher_command'], *map(str, pkg.get('launcher_args', []))])
    launcher = catalog_launcher(pkg['id'])
    write_launcher(launcher, name, command)
    update_details({launcher: (GameMetadata(name, pkg.get('description') or None), pkg.get('preview_url') or None)})
    reload_es()
    return launcher

def remove_catalog_game(pkg_id: str) -> None:
    catalog_launcher(pkg_id).unlink(missing_ok=True)
    update_gamelist(LINUX_GAMES_DIR, LAUNCHER_EXTENSION, {})
    reload_es()
