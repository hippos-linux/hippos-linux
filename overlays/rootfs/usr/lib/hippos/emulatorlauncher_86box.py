from __future__ import annotations

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _load_hippos_conf,
    _require_emulator_bin,
    _run_game_command,
)

from HipposPaths import BIOS
from emulatorlauncher_registry import Emulator, register

BOX86_ROM_DIR = BIOS / '86box'

def launch_86box(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('86box')
    vm_dir = ctx.rom.parent if ctx.rom.is_file() else ctx.rom
    cmd = [str(bin_path), '--vmpath', str(vm_dir), '--rompath', str(BOX86_ROM_DIR), '--fullscreen', '--noconfirm']
    env = _build_game_env(_load_hippos_conf(), ctx)
    return _run_game_command(ctx, cmd, env).returncode

register(Emulator('86box', launch_86box))
