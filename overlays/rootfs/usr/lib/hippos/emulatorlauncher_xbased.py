from __future__ import annotations

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _game_value,
    _load_hippos_conf,
    _run_game_command,
    _require_emulator_bin,
)

from HipposPaths import CONFIGS, SAVES
from emulatorlauncher_registry import Emulator, register

XBASED_CONFIG_FILE = CONFIGS / 'xbased' / 'xbased.ini'
XBASED_MANAGED_SETTINGS = {'update.check': '0', 'covers': '0'}

def write_xbased_config() -> None:
    XBASED_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = XBASED_CONFIG_FILE.read_text(encoding='utf-8').splitlines() if XBASED_CONFIG_FILE.exists() else []
    kept = [line for line in lines if line.split('=', 1)[0].strip() not in XBASED_MANAGED_SETTINGS]
    kept += [f'{key}={value}' for key, value in XBASED_MANAGED_SETTINGS.items()]
    XBASED_CONFIG_FILE.write_text('\n'.join(kept) + '\n', encoding='utf-8')

def launch_xbased(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('xbased')
    write_xbased_config()
    conf = _load_hippos_conf()
    cmd = [str(bin_path), '-c', str(XBASED_CONFIG_FILE), str(ctx.rom), 'fullscreen=1']
    for option, key in (('scale', 'xbased_scale'), ('aspect', 'xbased_aspect'), ('precision', 'xbased_precision')):
        if value := _game_value(conf, ctx, key):
            cmd.append(f'{option}={value}')
    env = _build_game_env(conf, ctx)
    env['XDG_DATA_HOME'] = str(SAVES / 'xbox')
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

register(Emulator('xbased', launch_xbased))
