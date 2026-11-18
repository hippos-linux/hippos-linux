from __future__ import annotations

from pathlib import Path

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _load_effective_hippos_conf,
    _log,
    _run_game_command,
    generate_sdl_game_controller_config,
    _require_emulator_bin,
)
from emulatorlauncher_registry import Emulator, register

from HipposPaths import CONFIGS, EMULATORS_ROOT, USERDATA

WAL_PACKAGE_DIR = EMULATORS_ROOT / 'windowsarcadeloader'
WAL_ROOT = CONFIGS / 'windowsarcadeloader'
WAL_PREFIX_DIR = USERDATA / 'wine-bottles' / 'windowsarcadeloader'
WINE_RUNNERS_DIR = Path('/opt/wine-builds')
WAL_RUNNER = 'wine-proton'

WAL_MACHINE_SETTINGS = f'''\
runners_dir: {WINE_RUNNERS_DIR}
runner: {WAL_RUNNER}
payloads_dir: {WAL_PACKAGE_DIR / 'payloads'}
input:
  exit_combo: []
'''

def _link(link: Path, target: Path) -> None:
    if link.is_symlink() and link.readlink() == target:
        return
    link.unlink(missing_ok=True)
    link.symlink_to(target)

def _prepare_root() -> None:
    WAL_ROOT.mkdir(parents=True, exist_ok=True)
    WAL_PREFIX_DIR.mkdir(parents=True, exist_ok=True)
    _link(WAL_ROOT / 'systemprofiles', WAL_PACKAGE_DIR / 'systemprofiles')
    _link(WAL_ROOT / 'wine-prefix', WAL_PREFIX_DIR)
    (WAL_ROOT / 'launcher.yaml').write_text(WAL_MACHINE_SETTINGS, encoding='utf-8')

def launch_windowsarcadeloader(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('windowsarcadeloader')
    if not (WINE_RUNNERS_DIR / WAL_RUNNER / 'bin' / 'wine').is_file():
        _log.error("Windows Arcade Loader: Wine runner missing: %s", WINE_RUNNERS_DIR / WAL_RUNNER)
        return 1

    _prepare_root()

    conf = _load_effective_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    env['WAL_PLAYER_PADS'] = ';'.join(c.device_path for c in ctx.controllers if c.device_path)

    cmd = [str(bin_path), 'run', str(ctx.rom), '--root', str(WAL_ROOT)]
    result = _run_game_command(ctx, cmd, env, cwd=WAL_ROOT)
    return result.returncode

register(Emulator('windowsarcadeloader', launch_windowsarcadeloader, binaries=('arcade-launcher',), writes_to_rom=True))
