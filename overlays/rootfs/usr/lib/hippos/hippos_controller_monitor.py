"""Background controller hot-plug monitor for emulatorlauncher.

Watches for joystick add/remove events via pyudev.
On change: rebuilds device-path map, updates ctx.controllers, restarts evmapy.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emulatorlauncher_impl import ControllerInfo, ESControllerProfile, LaunchContext

_log = logging.getLogger(__name__)

_lock: threading.Lock = threading.Lock()


def _js_devices() -> list[Path]:
    """Return sorted list of /dev/input/js* paths currently present."""
    return sorted(Path('/dev/input').glob('js*'))


def _vendor_product(js: Path) -> tuple[str, str]:
    """Read vendor/product hex from sysfs for a js device node."""
    try:
        # Resolve the underlying event device via sysfs
        real = js.resolve()
        name = real.name  # e.g. js0
        # Walk up to find id dir
        sysfs = Path(f'/sys/class/input/{name}')
        vendor  = (sysfs / 'device' / 'id' / 'vendor').read_text().strip()
        product = (sysfs / 'device' / 'id' / 'product').read_text().strip()
        return vendor, product
    except OSError:
        return '', ''


def _guid_prefix(vendor: str, product: str) -> str:
    """Build a partial GUID string (bus+vendor+product) for matching."""
    return f'{vendor.lower()}{product.lower()}'


def _rebuild_path_map(controllers: list[ControllerInfo]) -> dict[int, str]:
    """
    Return {controller.index: new_device_path}.

    Matching strategy:
    1. Try GUID vendor/product prefix against sysfs data.
    2. Fall back to index order (js0 → index 0, js1 → index 1, etc.).
    """
    js_paths = _js_devices()
    if not js_paths:
        return {}

    # Build sysfs info for each available js device
    js_info: list[tuple[Path, str]] = []
    for js in js_paths:
        v, p = _vendor_product(js)
        js_info.append((js, _guid_prefix(v, p)))

    result: dict[int, str] = {}

    for ctrl in controllers:
        ctrl_prefix = _guid_prefix(
            ctrl.guid[8:12] if len(ctrl.guid) >= 12 else '',
            ctrl.guid[16:20] if len(ctrl.guid) >= 20 else '',
        )

        # Try vendor/product match first
        matched = None
        for js, prefix in js_info:
            if prefix and ctrl_prefix and prefix == ctrl_prefix:
                matched = str(js)
                break

        # Fall back to index order
        if matched is None and ctrl.index < len(js_info):
            matched = str(js_info[ctrl.index][0])

        if matched:
            result[ctrl.index] = matched

    return result


def _reconfigure_evmapy(
    system: str,
    emulator: str,
    rom: Path,
    controllers: list[ControllerInfo],
    profiles: list[ESControllerProfile],
) -> None:
    from hippos_evmapy import HIPPOS_EVMAPY, _prepare
    _log.info("controller monitor: reconfiguring evmapy")
    subprocess.call([str(HIPPOS_EVMAPY), 'stop'],  stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    _prepare(system, emulator, rom, controllers, profiles)
    subprocess.call([str(HIPPOS_EVMAPY), 'start'], stderr=subprocess.DEVNULL)


def _monitor_loop(
    ctx: LaunchContext,
    profiles: list[ESControllerProfile],
    initial_paths: list[str],
) -> None:
    try:
        import pyudev
    except ImportError:
        _log.warning("controller monitor: pyudev not available, hot-plug disabled")
        return

    udev_ctx = pyudev.Context()
    monitor  = pyudev.Monitor.from_netlink(udev_ctx)
    monitor.filter_by(subsystem='input')
    _log.info("controller monitor: started (watching %d controllers)", len(ctx.controllers))

    for device in iter(monitor.poll, None):
        if device.properties.get('ID_INPUT_JOYSTICK') != '1':
            continue

        _log.info("controller monitor: joystick event '%s' on %s",
                  device.action, device.sys_path)

        time.sleep(1)  # let device settle

        with _lock:
            new_map = _rebuild_path_map(ctx.controllers)
            current_paths = [c.device_path for c in ctx.controllers]
            new_paths     = [new_map.get(c.index, c.device_path) for c in ctx.controllers]

            if current_paths == new_paths:
                _log.debug("controller monitor: no path change, skipping reconfigure")
                continue

            _log.info("controller monitor: paths changed %s → %s", current_paths, new_paths)
            for ctrl in ctx.controllers:
                if ctrl.index in new_map:
                    ctrl.device_path = new_map[ctrl.index]

        _reconfigure_evmapy(
            ctx.system, ctx.emulator, ctx.rom,
            ctx.controllers, profiles,
        )


def start_controller_monitor(
    ctx: LaunchContext,
    profiles: list[ESControllerProfile],
) -> threading.Thread:
    """Start and return the background monitor thread (daemon)."""
    initial_paths = [c.device_path for c in ctx.controllers]
    t = threading.Thread(
        target=_monitor_loop,
        args=(ctx, profiles, initial_paths),
        daemon=True,
        name='hippos-controller-monitor',
    )
    t.start()
    return t
