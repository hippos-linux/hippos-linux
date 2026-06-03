"""OverlayFS mount helpers for emulatorlauncher.

Stacks a writable overlay over a read-only lower directory so saves
persist to /userdata/saves while the source ROM stays immutable.
"""

from __future__ import annotations

import subprocess
import logging
from contextlib import contextmanager
from pathlib import Path

_log = logging.getLogger(__name__)

_OVERLAY_ROOT = Path('/var/run/hippos/overlays')


@contextmanager
def mount_overlayfs(lower: Path, upper_root: Path):
    """Mount overlayfs over *lower*, yield the mount point.

    Writes go to upper_root/upper/; kernel bookkeeping in upper_root/work/.
    Mount point is /var/run/hippos/overlays/<lower.name>.
    """
    upper = upper_root / 'upper'
    work  = upper_root / 'work'
    mount_point = _OVERLAY_ROOT / lower.name

    upper.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    mount_point.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            'mount', '-t', 'overlay', 'overlay',
            '-o', f'lowerdir={lower},upperdir={upper},workdir={work}',
            str(mount_point),
        ],
        check=True,
    )
    _log.info("overlayfs: mounted %s → %s (saves → %s)", lower, mount_point, upper)

    try:
        yield mount_point
    finally:
        subprocess.run(['umount', str(mount_point)], check=False)
        try:
            mount_point.rmdir()
        except OSError:
            pass
        # Remove empty work dir; leave upper (it holds saves).
        try:
            work.rmdir()
        except OSError:
            pass
        _log.info("overlayfs: unmounted %s", mount_point)
