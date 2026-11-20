from __future__ import annotations

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _load_hippos_conf,
    _require_emulator_bin,
    _run_game_command,
)

from HipposPaths import CONFIGS
from emulatorlauncher_registry import Emulator, register

STELLA_BASE_DIR = CONFIGS / 'stella'

def launch_stella(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('stella')
    STELLA_BASE_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [str(bin_path), '-basedir', str(STELLA_BASE_DIR), '-fullscreen', '1', '-confirmexit', '0', str(ctx.rom)]
    env = _build_game_env(_load_hippos_conf(), ctx)
    return _run_game_command(ctx, cmd, env).returncode

register(Emulator('stella', launch_stella))
