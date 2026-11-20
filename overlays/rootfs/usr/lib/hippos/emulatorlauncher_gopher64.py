from __future__ import annotations

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _load_hippos_conf,
    _require_emulator_bin,
    _run_game_command,
)

from HipposPaths import CONFIGS, SAVES
from emulatorlauncher_registry import Emulator, register

def launch_gopher64(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('gopher64')
    env = _build_game_env(_load_hippos_conf(), ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_DATA_HOME'] = str(SAVES / 'n64')
    env['XDG_CACHE_HOME'] = str(CONFIGS / 'gopher64' / 'cache')
    return _run_game_command(ctx, [str(bin_path), '--fullscreen', str(ctx.rom)], env).returncode

register(Emulator('gopher64', launch_gopher64))
