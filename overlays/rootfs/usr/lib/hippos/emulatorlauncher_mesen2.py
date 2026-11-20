from __future__ import annotations

import json

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _load_hippos_conf,
    _require_emulator_bin,
    _run_game_command,
)

from HipposPaths import BIOS, CONFIGS, SAVES
from emulatorlauncher_registry import Emulator, register

MESEN_HOME = CONFIGS / 'Mesen2'

def write_mesen_settings(system: str) -> None:
    saves_dir = SAVES / system
    saves_dir.mkdir(parents=True, exist_ok=True)
    MESEN_HOME.mkdir(parents=True, exist_ok=True)
    settings_file = MESEN_HOME / 'settings.json'
    settings = json.loads(settings_file.read_text(encoding='utf-8-sig')) if settings_file.exists() else {}
    settings.setdefault('Preferences', {}).update(
        AutomaticallyCheckForUpdates=False,
        SingleInstance=False,
        OverrideSaveDataFolder=True,
        SaveDataFolder=str(saves_dir),
        OverrideSaveStateFolder=True,
        SaveStateFolder=str(saves_dir),
    )
    settings_file.write_text(json.dumps(settings, indent=2), encoding='utf-8-sig')
    firmware = MESEN_HOME / 'Firmware'
    if not firmware.exists() and not firmware.is_symlink():
        firmware.symlink_to(BIOS)

def launch_mesen2(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('mesen2')
    write_mesen_settings(ctx.system)
    env = _build_game_env(_load_hippos_conf(), ctx)
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    return _run_game_command(ctx, [str(bin_path), str(ctx.rom)], env).returncode

register(Emulator('mesen2', launch_mesen2, binaries=('mesen',)))
