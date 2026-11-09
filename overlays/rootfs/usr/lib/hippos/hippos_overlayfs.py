
from __future__ import annotations

import subprocess
import logging
from contextlib import contextmanager
from pathlib import Path

_log = logging.getLogger(__name__)

_OVERLAY_ROOT = Path('/var/run/hippos/overlays')

_SUDO = ['sudo', '-n']

@contextmanager
def mount_overlayfs(lower: Path, upper_root: Path):
    upper = upper_root / 'upper'
    work  = upper_root / 'work'
    mount_point = _OVERLAY_ROOT / lower.name

    upper.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    mount_point.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            *_SUDO, 'mount', '-t', 'overlay', 'overlay',
            '-o', f'lowerdir={lower},upperdir={upper},workdir={work}',
            str(mount_point),
        ],
        check=True,
    )
    _log.info("overlayfs: mounted %s → %s (saves → %s)", lower, mount_point, upper)

    try:
        yield mount_point
    finally:
        subprocess.run([*_SUDO, 'umount', str(mount_point)], check=False)
        try:
            mount_point.rmdir()
        except OSError:
            pass
        try:
            work.rmdir()
        except OSError:
            pass
        _log.info("overlayfs: unmounted %s", mount_point)
