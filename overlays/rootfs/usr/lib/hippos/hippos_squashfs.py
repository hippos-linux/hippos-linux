
from __future__ import annotations

import subprocess
import logging
from contextlib import contextmanager
from pathlib import Path

_log = logging.getLogger(__name__)

_SQUASHFS_ROOT = Path('/var/run/hippos/squashfs')

_SUDO = ['sudo', '-n']

@contextmanager
def mount_squashfs(rom: Path):
    mount_point = _SQUASHFS_ROOT / rom.stem
    mount_point.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [*_SUDO, 'mount', str(rom), str(mount_point)],
        check=True,
    )
    _log.info("squashfs: mounted %s → %s", rom, mount_point)

    try:
        contents = list(mount_point.iterdir())
        if len(contents) == 1 and contents[0].is_file() and contents[0].stem == rom.stem:
            yield contents[0]
        else:
            yield mount_point
    finally:
        subprocess.run(
            [*_SUDO, 'umount', str(mount_point)],
            check=False,
        )
        try:
            mount_point.rmdir()
        except OSError:
            pass
        _log.info("squashfs: unmounted %s", mount_point)
