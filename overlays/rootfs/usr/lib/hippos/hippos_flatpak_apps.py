from __future__ import annotations

import os
import re
import shlex
import subprocess

FLATHUB_URL = 'https://dl.flathub.org/repo/flathub.flatpakrepo'
SESSION_USER = 'hippos'
APP_ID = re.compile(r'^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+){2,}$')


def _flatpak(*args: str) -> list[str]:
    command = ['flatpak', *args]
    return command if os.geteuid() != 0 else ['runuser', '-l', SESSION_USER, '-c', shlex.join(command)]


def valid_app_id(app_id: str) -> bool:
    return APP_ID.match(app_id) is not None


def installed(app_id: str) -> bool:
    return subprocess.run(_flatpak('info', '--user', app_id), capture_output=True).returncode == 0


def install(app_id: str) -> int:
    if not valid_app_id(app_id):
        return 1
    subprocess.run(_flatpak('remote-add', '--user', '--if-not-exists', 'flathub', FLATHUB_URL))
    return subprocess.run(_flatpak('install', '--user', '--noninteractive', '--assumeyes', 'flathub', app_id)).returncode


def remove(app_id: str) -> int:
    if not valid_app_id(app_id):
        return 1
    return subprocess.run(_flatpak('uninstall', '--user', '--noninteractive', '--assumeyes', app_id)).returncode
