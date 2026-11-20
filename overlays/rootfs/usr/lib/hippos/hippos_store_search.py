from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import hippos_flatpak_apps
from hippos_apt import image_packages, missing_packages, search_packages

FLATPAK_PREFIX = 'flatpak::'
APT_PREFIX = 'apt::'
RESULTS_PER_SOURCE = 40
APT_LISTS = Path('/var/lib/apt/lists')
APT_LISTS_MAX_AGE_S = 24 * 3600
APT_PACKAGE_NAME = re.compile(r'^[a-z0-9][a-z0-9+.-]+$')
APT_NON_APP_PACKAGE = re.compile(r'^lib|-(dev|dbg|dbgsym|doc|data|common)$')
_APT_ENV = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}


class StoreSearchError(Exception):
    pass


@dataclass(frozen=True)
class SearchResult:
    name: str
    title: str
    description: str
    version: str
    source: str
    installed: bool


def is_search_result(name: str) -> bool:
    return name.startswith((FLATPAK_PREFIX, APT_PREFIX))


def search(term: str) -> list[SearchResult]:
    return flathub_results(term) + debian_results(term)


def flathub_results(term: str) -> list[SearchResult]:
    installed = hippos_flatpak_apps.installed_app_ids()
    return [SearchResult(f'{FLATPAK_PREFIX}{app.app_id}', app.name, app.description, app.version or 'latest',
                         'Flathub', app.app_id in installed)
            for app in hippos_flatpak_apps.search_flathub(term)[:RESULTS_PER_SOURCE]]


def _refresh_apt_lists() -> None:
    lists = list(APT_LISTS.glob('*_InRelease'))
    if lists and time.time() - max(p.stat().st_mtime for p in lists) < APT_LISTS_MAX_AGE_S:
        return
    subprocess.run(['sudo', '-n', 'apt-get', 'update', '-qq'], env=_APT_ENV, check=False)


def debian_results(term: str) -> list[SearchResult]:
    _refresh_apt_lists()
    system = image_packages() or frozenset()
    packages = [(name, description) for name, description in search_packages(term)
                if name not in system and not APT_NON_APP_PACKAGE.search(name)][:RESULTS_PER_SOURCE]
    missing = set(missing_packages([name for name, _ in packages]))
    return [SearchResult(f'{APT_PREFIX}{name}', name, description, 'latest', 'Debian', name not in missing)
            for name, description in packages]


def _apt_package(name: str) -> str:
    package = name[len(APT_PREFIX):]
    if not APT_PACKAGE_NAME.match(package):
        raise StoreSearchError(f"'{package}' is not a package name")
    if package in (image_packages() or frozenset()):
        raise StoreSearchError(f'{package} is part of HippOS and is updated with the system')
    return package


def install(name: str) -> None:
    if name.startswith(FLATPAK_PREFIX):
        app_id = name[len(FLATPAK_PREFIX):]
        if hippos_flatpak_apps.installed(app_id):
            print(f'Updating {app_id} from Flathub...', flush=True)
            result = hippos_flatpak_apps.update(app_id)
        else:
            print(f'Installing {app_id} from Flathub...', flush=True)
            result = hippos_flatpak_apps.install_from_flathub(app_id)
        if result != 0:
            raise StoreSearchError('Flathub install failed')
        return
    package = _apt_package(name)
    print(f'Installing {package} via apt...', flush=True)
    subprocess.run(['sudo', '-n', 'apt-get', 'update', '-qq'], env=_APT_ENV, check=False)
    result = subprocess.run(['sudo', '-n', 'apt-get', 'install', '-y', '--no-install-recommends', package],
                            env=_APT_ENV, check=False).returncode
    if result != 0:
        raise StoreSearchError(f'apt install failed (exit {result})')


def remove(name: str) -> None:
    if name.startswith(FLATPAK_PREFIX):
        if hippos_flatpak_apps.remove(name[len(FLATPAK_PREFIX):]) != 0:
            raise StoreSearchError('Flathub removal failed')
        return
    package = _apt_package(name)
    result = subprocess.run(['sudo', '-n', 'apt-get', 'remove', '-y', package], env=_APT_ENV, check=False).returncode
    if result != 0:
        raise StoreSearchError(f'apt remove failed (exit {result})')
