"""In-game power settings: CPU power mode (powermode), ACPI platform profile
(platformprofile) and AMD TDP (tdp, % of the detected maximum).

Each setting resolves game > folder > system > global and is put back when the
emulator exits. hippos-power-mode and hippos-tdp own the hardware access;
this module only decides what to apply and when.
"""
from __future__ import annotations

import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from emulatorlauncher_shared import _conf_value, _log

_POWER_MODE_TOOL = '/usr/lib/hippos/hippos-power-mode'
_TDP_TOOL = '/usr/lib/hippos/hippos-tdp'

# Firmware applies a platform profile's own power limits about a second after
# the switch, overwriting any TDP set in the meantime.
_PROFILE_SETTLE_SECONDS = 2


def _game_setting(conf: dict[str, str], system: str, rom: Path, name: str) -> str:
    """Per-game, per-folder or per-system override only; '' when unset."""
    for key in (
        f'{system}["{rom.stem}"].{name}',
        f'{system}.folder["{rom.parent}"].{name}',
        f'{system}.{name}',
    ):
        if value := _conf_value(conf, key, ''):
            return value
    return ''


def _run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(args), capture_output=True, text=True, check=False)
    for line in (result.stdout + result.stderr).splitlines():
        _log.info("%s", line)
    return result


def _run_detached(*args: str) -> None:
    """For restores: ryzenadj (plus any settle wait) would hold up the return
    to ES. hippos-tdp's lock keeps a following launch behind it."""
    subprocess.Popen(
        list(args),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


@contextmanager
def game_power_settings(conf: dict[str, str], system: str, rom: Path) -> Iterator[None]:
    # Global profile/TDP are already active from boot; only overrides need
    # applying and undoing. The power mode is (re)applied every launch so a
    # global change made in ES takes effect without waiting for an AC event.
    power_mode = _game_setting(conf, system, rom, 'powermode')
    _run_tool(_POWER_MODE_TOOL, power_mode or 'default')

    profile = _game_setting(conf, system, rom, 'platformprofile')
    tdp = _game_setting(conf, system, rom, 'tdp')
    if profile or tdp:
        # Without a global TDP, restore puts back the limits from before the game.
        _run_tool(_TDP_TOOL, 'save')

    profile_changed = False
    previous_profile = ''
    if profile:
        previous_profile = subprocess.run(
            [_TDP_TOOL, 'profile'], capture_output=True, text=True, check=False,
        ).stdout.strip()
        profile_changed = _run_tool(_TDP_TOOL, 'profile', profile).returncode == 0
        if not profile_changed:
            _log.info("Platform profile %s not applied (unsupported or already active)", profile)

    # Applied off the launch path so the profile settle delay doesn't hold up
    # the emulator start.
    tdp_thread: threading.Thread | None = None
    if tdp:
        settle = str(_PROFILE_SETTLE_SECONDS if profile_changed else 0)
        tdp_thread = threading.Thread(target=_run_tool, args=(_TDP_TOOL, 'set', tdp, settle), daemon=True)
        tdp_thread.start()

    try:
        yield
    finally:
        if tdp_thread is not None:
            tdp_thread.join()

        if profile_changed:
            restore_profile = _conf_value(conf, 'global.platformprofile', '') or previous_profile
            if restore_profile:
                _run_tool(_TDP_TOOL, 'profile', restore_profile)

        # A profile switch resets the firmware's power limits, so the TDP has
        # to follow it even without a per-game TDP.
        if tdp_thread is not None or profile_changed:
            _run_detached(_TDP_TOOL, 'restore', str(_PROFILE_SETTLE_SECONDS if profile_changed else 0))

        if power_mode:
            _run_tool(_POWER_MODE_TOOL, 'default')
