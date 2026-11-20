from __future__ import annotations

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _load_hippos_conf,
    _run_game_command,
)

from emulatorlauncher_registry import Emulator, register

WAYDROID_LAUNCHER = '/usr/lib/hippos/waydroid-launcher'

def launch_waydroid(ctx: LaunchContext) -> int:
    env = _build_game_env(_load_hippos_conf(), ctx)
    return _run_game_command(ctx, [WAYDROID_LAUNCHER, str(ctx.rom)], env).returncode

register(Emulator('waydroid', launch_waydroid))
