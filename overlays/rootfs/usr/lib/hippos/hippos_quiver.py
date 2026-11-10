from __future__ import annotations

import platform
from pathlib import Path

APP_ID = 'io.github.tgeorgiadis.QuiverLauncher'
USERDATA = Path('/userdata')
RELEASE_URL = 'https://github.com/tgeorgiadis/quiver-launcher/releases/download/v3.5.1'

if platform.machine() == 'aarch64':
    DOWNLOAD_URL = f'{RELEASE_URL}/QuiverLauncher-linux-arm64.AppImage'
    DOWNLOAD_SHA256 = 'd1d84d2dc38e68999dc65d7a53cf09005bf7db5f17e85b585c1d3e170822fb18'
    INSTALL_DIR = USERDATA / '.local' / 'share' / 'hippos' / 'quiver'
    SHARE_DIR = INSTALL_DIR / 'usr' / 'share'
    DATA_DIR = USERDATA / '.local' / 'share' / 'QuiverLauncher'
    LAUNCH_COMMAND = [str(INSTALL_DIR / 'AppRun')]
else:
    DOWNLOAD_URL = f'{RELEASE_URL}/QuiverLauncher.flatpak'
    DOWNLOAD_SHA256 = 'd6629e54f7967433f5717253381961fddb5056bd7560c0c9c7370dd0dcb65c61'
    INSTALL_DIR = USERDATA / '.local' / 'share' / 'flatpak' / 'app' / APP_ID
    SHARE_DIR = INSTALL_DIR / 'current' / 'active' / 'export' / 'share'
    DATA_DIR = USERDATA / '.var' / 'app' / APP_ID / 'data' / 'QuiverLauncher'
    LAUNCH_COMMAND = ['/usr/bin/flatpak', 'run', APP_ID]
