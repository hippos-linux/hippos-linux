from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import yaml

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_int,
    _conf_value,
    _find_emulator_bin,
    _load_hippos_conf,
    _log,
    _run_game_command,
)

from HipposPaths import BIOS, CONFIGS, SAVES

VITA3K_CONFIG_FILE = CONFIGS / 'Vita3K' / 'config.yml'
VITA3K_PREF_DIR    = SAVES / 'psvita'
VITA3K_RETROBAT_PREF_DIR = SAVES / 'psvita' / 'vita3k'
VITA3K_TITLE_ID    = re.compile(r'[A-Z]{4}\d{5}')
VITA3K_OLD_PREF_DIR = SAVES / 'psvita' / 'Vita3K' / 'Vita3K'
VITA3K_FIRMWARE_FILES = ('PSVUPDAT.PUP', 'PSP2UPDAT.PUP')
VITA3K_FIRMWARE_DIRS  = (BIOS / 'psvita', BIOS)

def _setting_on(raw: str, default: bool) -> bool:
    return default if raw == '' else raw.lower() in ('1', 'true', 'on')

def _migrate_old_pref_dir() -> None:
    if not VITA3K_OLD_PREF_DIR.is_dir():
        return
    VITA3K_PREF_DIR.mkdir(parents=True, exist_ok=True)
    for item in VITA3K_OLD_PREF_DIR.iterdir():
        if not (VITA3K_PREF_DIR / item.name).exists():
            shutil.move(item, VITA3K_PREF_DIR / item.name)
    for folder in (VITA3K_OLD_PREF_DIR, VITA3K_OLD_PREF_DIR.parent):
        try:
            folder.rmdir()
        except OSError:
            break

def _update_vita3k_config(bin_path: Path, env: dict[str, str], conf: dict[str, str], pref_dir: Path) -> None:
    if not VITA3K_CONFIG_FILE.exists():
        subprocess.run([str(bin_path), '--help'], env=env, cwd=bin_path.parent,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    config = yaml.safe_load(VITA3K_CONFIG_FILE.read_text()) or {}
    config['pref-path'] = f'{pref_dir}/'
    config['initial-setup'] = False
    config['show-welcome'] = False
    config['check-for-updates-mode'] = 0
    config['resolution-multiplier'] = _conf_int(conf, 'global.vita3k_resolution', 1)
    config['enable-fxaa'] = _setting_on(_conf_value(conf, 'global.vita3k_fxaa', ''), False)
    config['v-sync'] = _setting_on(_conf_value(conf, 'global.vita3k_vsync', ''), True)
    config['anisotropic-filtering'] = _conf_int(conf, 'global.vita3k_anisotropic', 1)
    config['enable-linear-filter'] = _setting_on(_conf_value(conf, 'global.vita3k_linear', ''), False)
    config['disable-surface-sync'] = _setting_on(_conf_value(conf, 'global.vita3k_surface', ''), True)
    VITA3K_CONFIG_FILE.write_text(yaml.dump(config, default_flow_style=False, explicit_start=True))

def _has_firmware(pref_dir: Path) -> bool:
    return (pref_dir / 'vs0' / 'sys' / 'external').is_dir()

def firmware_installed() -> bool:
    return any(_has_firmware(d) for d in (VITA3K_PREF_DIR, VITA3K_RETROBAT_PREF_DIR))

def find_firmware() -> list[Path]:
    found = []
    for name in VITA3K_FIRMWARE_FILES:
        found += [d / name for d in VITA3K_FIRMWARE_DIRS if (d / name).is_file()][:1]
    return found

def _title_id(rom: Path) -> Optional[str]:
    begin, end = rom.stem.find('['), rom.stem.rfind(']')
    if 0 <= begin < end:
        return rom.stem[begin + 1: end]
    if rom.is_file() and rom.stat().st_size < 64:
        content = rom.read_text(errors='replace').strip()
        if VITA3K_TITLE_ID.fullmatch(content):
            return content
    return None

def _pick_pref_dir(title_id: Optional[str]) -> Path:
    candidates = (VITA3K_PREF_DIR, VITA3K_RETROBAT_PREF_DIR)
    if title_id:
        for pref_dir in candidates:
            if (pref_dir / 'ux0' / 'app' / title_id).is_dir():
                return pref_dir
    return next((d for d in candidates if _has_firmware(d)), VITA3K_PREF_DIR)

def _install_missing_firmware(bin_path: Path, env: dict[str, str], pref_dir: Path) -> None:
    if _has_firmware(pref_dir):
        return
    for pup in find_firmware():
        _log.info("Installing Vita firmware from %s", pup)
        subprocess.run([str(bin_path), '--firmware', str(pup)],
                       env=env, cwd=bin_path.parent, check=False)

def launch_vita3k(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('vita3k')
    if bin_path is None:
        _log.error("vita3k not found")
        return 1
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_DATA_HOME'] = str(SAVES / 'psvita')
    _migrate_old_pref_dir()
    title_id = _title_id(ctx.rom)
    pref_dir = _pick_pref_dir(title_id)
    _update_vita3k_config(bin_path, env, conf, pref_dir)
    _install_missing_firmware(bin_path, env, pref_dir)
    cmd = [str(bin_path), '-F', '-B', _conf_value(conf, 'global.vita3k_gfxbackend', 'Vulkan')]
    if title_id and (pref_dir / 'ux0' / 'app' / title_id).is_dir():
        cmd += ['-r', title_id]
    else:
        cmd.append(str(ctx.rom))
    result = _run_game_command(ctx, 'vita3k', cmd, env, cwd=bin_path.parent)
    return result.returncode
