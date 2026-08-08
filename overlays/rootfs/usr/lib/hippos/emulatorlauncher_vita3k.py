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


VITA3K_CONFIG_DIR  = CONFIGS / 'vita3k'
VITA3K_CONFIG_FILE = VITA3K_CONFIG_DIR / 'config.yml'


def _write_vita3k_config(conf: dict[str, str]) -> None:
    """Write Vita3K config.yml (YAML key-value pairs).

    ruamel.yaml is not guaranteed available; write raw YAML lines instead
    to preserve the vita3k format expectation. If yaml is available use it.
    """
    VITA3K_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (SAVES / 'psvita').mkdir(parents=True, exist_ok=True)

    backend    = _conf_value(conf, 'global.vita3k_gfxbackend', 'OpenGL')
    resolution = _conf_int(conf,   'global.vita3k_resolution', 1)
    fxaa_raw   = _conf_value(conf, 'global.vita3k_fxaa', '')
    vsync_raw  = _conf_value(conf, 'global.vita3k_vsync', '')
    aniso      = _conf_int(conf,   'global.vita3k_anisotropic', 1)
    linear_raw = _conf_value(conf, 'global.vita3k_linear', '')
    surface_raw = _conf_value(conf, 'global.vita3k_surface', '')

    fxaa    = 'true' if fxaa_raw.lower() in ('1', 'true', 'on') else 'false'
    vsync   = 'true' if vsync_raw == '' or vsync_raw.lower() in ('1', 'true', 'on') else 'false'
    linear  = 'true' if linear_raw.lower() in ('1', 'true', 'on') else 'false'
    surface = 'true' if surface_raw == '' or surface_raw.lower() in ('1', 'true', 'on') else 'false'

    if _HAS_YAML:
        existing: dict = {}
        if VITA3K_CONFIG_FILE.exists():
            try:
                existing = yaml.safe_load(VITA3K_CONFIG_FILE.read_text()) or {}
            except Exception:
                existing = {}
        existing['pref-path']            = str(SAVES / 'psvita')
        existing['backend-renderer']     = backend
        existing['resolution-multiplier'] = resolution
        existing['enable-fxaa']          = fxaa
        existing['v-sync']               = vsync
        existing['anisotropic-filtering'] = aniso
        existing['enable-linear-filter'] = linear
        existing['disable-surface-sync'] = surface
        VITA3K_CONFIG_FILE.write_text(yaml.dump(existing, default_flow_style=False))
    else:
        # Fallback: write minimal YAML key-value pairs
        lines = [
            '---',
            f'pref-path: {SAVES / "psvita"}',
            f'backend-renderer: {backend}',
            f'resolution-multiplier: {resolution}',
            f'enable-fxaa: {fxaa}',
            f'v-sync: {vsync}',
            f'anisotropic-filtering: {aniso}',
            f'enable-linear-filter: {linear}',
            f'disable-surface-sync: {surface}',
        ]
        VITA3K_CONFIG_FILE.write_text('\n'.join(lines) + '\n')

    _log.info("Wrote Vita3K config: %s", VITA3K_CONFIG_FILE)


def launch_vita3k(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('vita3k')
    if bin_path is None:
        _log.error("vita3k not found")
        return 1
    (SAVES / 'psvita').mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_vita3k_config(conf)
    # Derive app ID from rom filename: e.g. [PCSA00011].psvita -> PCSA00011
    rom_stem = ctx.rom.stem
    begin, end = rom_stem.find('['), rom_stem.rfind(']')
    if 0 <= begin < end:
        app_id = rom_stem[begin + 1: end]
        app_dir = SAVES / 'psvita' / 'ux0' / 'app' / app_id
        if app_dir.is_dir():
            cmd = [str(bin_path), '-F', '-w', '-f', '-c', str(VITA3K_CONFIG_FILE), '-r', app_id]
        else:
            cmd = [str(bin_path), '-F', '-w', '-f', '-c', str(VITA3K_CONFIG_FILE), str(ctx.rom)]
    else:
        cmd = [str(bin_path), '-F', '-w', '-f', '-c', str(VITA3K_CONFIG_FILE), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    result = _run_game_command(ctx, 'vita3k', cmd, env, cwd=bin_path.parent)
    return result.returncode
