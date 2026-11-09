from __future__ import annotations

from pathlib import Path

APP_ID = 'io.github.tgeorgiadis.QuiverLauncher'
USERDATA = Path('/userdata')
FLATPAK_INSTALL = USERDATA / '.local' / 'share' / 'flatpak' / 'app' / APP_ID
DATA_DIR = USERDATA / '.var' / 'app' / APP_ID / 'data' / 'QuiverLauncher'
