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

LUNARIA_CONFIG = CONFIGS / 'lunaria' / 'lunaria.conf'
LUNARIA_FRAMEWORK_RES = CONFIGS / 'lunaria' / 'framework-res'
LUNARIA_DATA_ROOT = SAVES / 'android' / 'lunaria'

def launch_lunaria(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('lunaria')
    LUNARIA_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    LUNARIA_CONFIG.touch(exist_ok=True)
    LUNARIA_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    env = _build_game_env(_load_hippos_conf(), ctx)
    if LUNARIA_FRAMEWORK_RES.is_dir():
        env['LUNARIA_FRAMEWORK_RES'] = str(LUNARIA_FRAMEWORK_RES)
    env['LUNARIA_FULLSCREEN'] = '1'
    cmd = [str(bin_path), '--config', str(LUNARIA_CONFIG), '--data-root', str(LUNARIA_DATA_ROOT), str(ctx.rom)]
    return _run_game_command(ctx, cmd, env, cwd=bin_path.parent).returncode

register(Emulator('lunaria', launch_lunaria))
