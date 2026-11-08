from __future__ import annotations

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

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

from HipposPaths import CONFIGS, SAVES


VITA3K_CONFIG_FILE = CONFIGS / 'Vita3K' / 'config.yml'
VITA3K_PREF_DIR    = SAVES / 'psvita' / 'Vita3K' / 'Vita3K'


def _setting_on(raw: str, default: bool) -> bool:
    return default if raw == '' else raw.lower() in ('1', 'true', 'on')


def _update_vita3k_config(conf: dict[str, str]) -> None:
    """Vita3K rejects a config missing any key and writes a complete one when it
    first starts, so settings are only merged once that file exists."""
    if not _HAS_YAML or not VITA3K_CONFIG_FILE.exists():
        return
    config = yaml.safe_load(VITA3K_CONFIG_FILE.read_text()) or {}
    config['resolution-multiplier'] = _conf_int(conf, 'global.vita3k_resolution', 1)
    config['enable-fxaa'] = _setting_on(_conf_value(conf, 'global.vita3k_fxaa', ''), False)
    config['v-sync'] = _setting_on(_conf_value(conf, 'global.vita3k_vsync', ''), True)
    config['anisotropic-filtering'] = _conf_int(conf, 'global.vita3k_anisotropic', 1)
    config['enable-linear-filter'] = _setting_on(_conf_value(conf, 'global.vita3k_linear', ''), False)
    config['disable-surface-sync'] = _setting_on(_conf_value(conf, 'global.vita3k_surface', ''), True)
    VITA3K_CONFIG_FILE.write_text(yaml.dump(config, default_flow_style=False))


def launch_vita3k(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('vita3k')
    if bin_path is None:
        _log.error("vita3k not found")
        return 1
    conf = _load_hippos_conf()
    _update_vita3k_config(conf)
    cmd = [str(bin_path), '-F', '-B', _conf_value(conf, 'global.vita3k_gfxbackend', 'OpenGL')]
    # Derive app ID from rom filename: e.g. [PCSA00011].psvita -> PCSA00011
    rom_stem = ctx.rom.stem
    begin, end = rom_stem.find('['), rom_stem.rfind(']')
    app_dir = VITA3K_PREF_DIR / 'ux0' / 'app' / rom_stem[begin + 1: end] if 0 <= begin < end else None
    if app_dir is not None and app_dir.is_dir():
        cmd += ['-r', app_dir.name]
    else:
        cmd.append(str(ctx.rom))
    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    env['XDG_CONFIG_HOME'] = str(CONFIGS)
    env['XDG_DATA_HOME'] = str(SAVES / 'psvita')
    result = _run_game_command(ctx, 'vita3k', cmd, env, cwd=bin_path.parent)
    return result.returncode
