from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

FLATHUB_URL = 'https://dl.flathub.org/repo/flathub.flatpakrepo'
SESSION_USER = 'hippos'
CLAIMS = Path('/userdata/system/linux-apps-flatpak-claims')
APP_ID = re.compile(r'^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+){2,}$')


def _flatpak(*args: str) -> list[str]:
    command = ['flatpak', *args]
    return command if os.geteuid() != 0 else ['runuser', '-l', SESSION_USER, '-c', shlex.join(command)]


def valid_app_id(app_id: str) -> bool:
    return APP_ID.match(app_id) is not None


def claimed_apps() -> set[str]:
    try:
        return set(CLAIMS.read_text(encoding='utf-8').split())
    except FileNotFoundError:
        return set()


def _set_claimed(app_id: str, claimed: bool) -> None:
    current = claimed_apps()
    updated = current | {app_id} if claimed else current - {app_id}
    if updated != current:
        CLAIMS.write_text(''.join(f'{app}\n' for app in sorted(updated)), encoding='utf-8')


def installed(app_id: str) -> bool:
    return subprocess.run(_flatpak('info', '--user', app_id), capture_output=True).returncode == 0


def install(app_id: str) -> int:
    if not valid_app_id(app_id):
        return 1
    _set_claimed(app_id, True)
    subprocess.run(_flatpak('remote-add', '--user', '--if-not-exists', 'flathub', FLATHUB_URL))
    result = subprocess.run(_flatpak('install', '--user', '--noninteractive', '--assumeyes', 'flathub', app_id)).returncode
    if result != 0 and not installed(app_id):
        _set_claimed(app_id, False)
    return result


def remove(app_id: str) -> int:
    if not valid_app_id(app_id):
        return 1
    result = subprocess.run(_flatpak('uninstall', '--user', '--noninteractive', '--assumeyes', app_id)).returncode
    if not installed(app_id):
        _set_claimed(app_id, False)
    return result
