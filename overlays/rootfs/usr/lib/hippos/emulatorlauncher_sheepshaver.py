from __future__ import annotations

from emulatorlauncher_shared import (
    LaunchContext,
    _log,
    _build_game_env,
    _load_hippos_conf,
    _require_emulator_bin,
    _run_game_command,
)

from HipposPaths import BIOS, CONFIGS
from emulatorlauncher_registry import Emulator, register

SHEEPSHAVER_ROM_DIR = BIOS / 'sheepshaver'
SHEEPSHAVER_PREFS = CONFIGS / 'sheepshaver' / 'prefs'

def launch_sheepshaver(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('sheepshaver')
    mac_rom = next((path for path in sorted(SHEEPSHAVER_ROM_DIR.glob('*'))
                    if path.name == 'Mac OS ROM' or path.suffix.lower() == '.rom'), None)
    if mac_rom is None:
        _log.error("sheepshaver: no PowerPC Mac ROM ('Mac OS ROM' or *.rom) in %s", SHEEPSHAVER_ROM_DIR)
        return 1
    managed = {
        'rom': str(mac_rom),
        'disk': str(ctx.rom),
        'nogui': 'true',
        'jit': 'true',
        'screen': 'dga/0/0',
    }
    SHEEPSHAVER_PREFS.parent.mkdir(parents=True, exist_ok=True)
    lines = SHEEPSHAVER_PREFS.read_text(encoding='utf-8').splitlines() if SHEEPSHAVER_PREFS.exists() else []
    kept = [line for line in lines if line.split(' ', 1)[0] not in managed]
    SHEEPSHAVER_PREFS.write_text('\n'.join([*kept, *(f'{key} {value}' for key, value in managed.items())]) + '\n',
                                 encoding='utf-8')
    cmd = [str(bin_path), '--config', str(SHEEPSHAVER_PREFS)]
    env = _build_game_env(_load_hippos_conf(), ctx)
    return _run_game_command(ctx, cmd, env).returncode

register(Emulator('sheepshaver', launch_sheepshaver))
