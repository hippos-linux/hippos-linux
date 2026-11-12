from __future__ import annotations

import zipfile
from pathlib import Path

from HipposPaths import BIOS, SAVES

IMAGE_PATTERNS = ('Windows 9*.img', 'Windows 9*.vhd', 'win9*.img', 'win9*.vhd')
DOSBOX_PURE_SAVES = SAVES / 'win98'

def base_image() -> Path | None:
    for pattern in IMAGE_PATTERNS:
        if found := sorted(BIOS.glob(pattern)):
            return found[0]
    return None

def preset_dosbox_pure_autoboot(rom: Path) -> None:
    save = DOSBOX_PURE_SAVES / f'{rom.stem}.pure.zip'
    image = base_image()
    if image is None or save.exists() or save.with_suffix('').with_suffix('.sav').exists():
        return
    DOSBOX_PURE_SAVES.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(save, 'w') as archive:
        archive.writestr('AUTOBOOT.DBP', f'O*{image.stem}')
