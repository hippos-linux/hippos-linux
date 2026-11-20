from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

FLATHUB_URL = 'https://dl.flathub.org/repo/flathub.flatpakrepo'
SESSION_USER = 'hippos'
CLAIMS = Path('/userdata/system/linux-apps-flatpak-claims')
GAME_CLAIMS = Path('/userdata/system/linux-games-flatpak-claims')
APP_ID = re.compile(r'^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+){2,}$')


def _flatpak(*args: str) -> list[str]:
    command = ['flatpak', *args]
    return command if os.geteuid() != 0 else ['runuser', '-l', SESSION_USER, '-c', shlex.join(command)]


def valid_app_id(app_id: str) -> bool:
    return APP_ID.match(app_id) is not None


def _read_claims(claims: Path) -> set[str]:
    try:
        return set(claims.read_text(encoding='utf-8').split())
    except FileNotFoundError:
        return set()


def claimed_apps() -> set[str]:
    return _read_claims(CLAIMS)


def claimed_games() -> set[str]:
    return _read_claims(GAME_CLAIMS)


def _claims_for(game: bool) -> Path:
    return GAME_CLAIMS if game else CLAIMS


def _set_claimed(app_id: str, claimed: bool, game: bool = False) -> None:
    claims = _claims_for(game)
    current = _read_claims(claims)
    updated = current | {app_id} if claimed else current - {app_id}
    if updated != current:
        claims.write_text(''.join(f'{app}\n' for app in sorted(updated)), encoding='utf-8')


def installed(app_id: str) -> bool:
    return subprocess.run(_flatpak('info', '--user', app_id), capture_output=True).returncode == 0


def _add_flathub() -> None:
    subprocess.run(_flatpak('remote-add', '--user', '--if-not-exists', 'flathub', FLATHUB_URL))


def install(app_id: str, game: bool = False) -> int:
    if not valid_app_id(app_id):
        return 1
    _set_claimed(app_id, False, not game)
    _set_claimed(app_id, True, game)
    result = install_from_flathub(app_id)
    if result != 0 and not installed(app_id):
        _set_claimed(app_id, False, game)
    return result


def install_from_flathub(app_id: str) -> int:
    if not valid_app_id(app_id):
        return 1
    _add_flathub()
    return subprocess.run(_flatpak('install', '--user', '--noninteractive', '--assumeyes', 'flathub', app_id)).returncode


def update(app_id: str) -> int:
    if not valid_app_id(app_id):
        return 1
    return subprocess.run(_flatpak('update', '--user', '--noninteractive', '--assumeyes', app_id)).returncode


def installed_app_ids() -> set[str]:
    listing = subprocess.run(_flatpak('list', '--user', '--app', '--columns=application'),
                             capture_output=True, text=True, check=False).stdout
    return set(listing.split())


@dataclass(frozen=True)
class FlathubApp:
    app_id: str
    name: str
    description: str
    version: str


def search_flathub(term: str) -> list[FlathubApp]:
    _add_flathub()
    subprocess.run(_flatpak('update', '--user', '--appstream', 'flathub'), capture_output=True, check=False)
    listing = subprocess.run(_flatpak('search', '--user', '--columns=application,name,description,version', term),
                             capture_output=True, text=True, check=False).stdout
    apps = []
    for line in listing.splitlines():
        fields = line.split('\t')
        if len(fields) == 4 and valid_app_id(fields[0]):
            apps.append(FlathubApp(*fields))
    return apps


def remove(app_id: str) -> int:
    if not valid_app_id(app_id):
        return 1
    result = subprocess.run(_flatpak('uninstall', '--user', '--noninteractive', '--assumeyes', app_id)).returncode
    if not installed(app_id):
        _set_claimed(app_id, False)
        _set_claimed(app_id, False, True)
    return result
