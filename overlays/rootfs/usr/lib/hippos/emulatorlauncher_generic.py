from __future__ import annotations

from emulatorlauncher_impl import (
    RETROARCH_BIN,
    SAVES,
    USERDATA,
    LaunchContext,
    _build_game_env,
    _load_hippos_conf,
    _log,
    _run_game_command,
    _write_retroarch_game_overrides,
    _write_retroarch_config,
    _write_retroarch_core_options,
    _core_search_paths,
    find_core,
)


def launch_libretro(ctx: LaunchContext) -> int:
    if not ctx.core:
        _log.error("No core configured for system '%s'", ctx.system)
        return 1

    core_path = find_core(ctx.core)
    if core_path is None:
        _log.error(
            "Core '%s_libretro.so' not found. Searched:\n  %s",
            ctx.core,
            '\n  '.join(str(p) for p in _core_search_paths()),
        )
        return 1

    conf = _load_hippos_conf()
    _write_retroarch_core_options(ctx, conf)
    ra_cfg = _write_retroarch_config(ctx.controllers, ctx)
    ra_game_cfg = _write_retroarch_game_overrides(ctx)
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    cmd = [
        str(RETROARCH_BIN),
        '--verbose',
        '--log-file', str(USERDATA / 'system' / 'logs' / 'retroarch.log'),
        '-L', str(core_path),
        '--config', str(ra_cfg),
    ]
    if ra_game_cfg is not None:
        cmd += ['--appendconfig', str(ra_game_cfg)]
    cmd.append(str(ctx.rom))
    _log.info("Launching: %s", ' '.join(cmd))

    env = _build_game_env(conf, ctx)
    try:
        result = _run_game_command(ctx, 'retroarch', cmd, env)
    finally:
        if ra_game_cfg is not None:
            ra_game_cfg.unlink(missing_ok=True)
    return result.returncode


# Emulators that accept a CLI fullscreen flag before the ROM argument.
# Quake-engine ports use Quake console syntax (+set), others use standard flags.
_FULLSCREEN_FLAGS: dict[str, list[str]] = {
    # Quake-engine ports
    'vkquake':        ['-fullscreen'],
    'vkquake2':       ['-fullscreen'],
    'vkquake3':       ['-fullscreen'],
    'yquake2':        ['-fullscreen'],
    'iortcw':         ['+set', 'r_fullscreen', '1'],
    'openjk':         ['+set', 'r_fullscreen', '1'],
    'openjkdf2':      ['+set', 'r_fullscreen', '1'],
    'openmohaa':      ['+set', 'r_fullscreen', '1'],
    'dhewm3':         ['+set', 'r_fullscreen', '1'],
    'etlegacy':       ['+set', 'r_fullscreen', '1'],
    # Other ports still on _launch_standalone
    'devilutionx':    ['--fullscreen'],
    'raze':           ['-fullscreen'],
    'ecwolf':         ['--fullscreen'],
    'xash3d_fwgs':    ['-fullscreen'],
    'dxx-rebirth':    ['--fullscreen'],
    'hurrican':       ['--fullscreen'],
    'openjazz':       ['-f'],
    'jazz2-native':   ['--fullscreen'],
    'cdogs':          ['--fullscreen'],
    'cgenius':        ['--fullscreen'],
    'sdlpop':         ['--fullscreen'],
    'mugen':          ['-f'],
}


def launch_standalone(ctx: LaunchContext) -> int:
    """Generic launcher for standalone emulators under /opt/emulators or user path."""
    from emulatorlauncher_impl import _find_emulator_bin

    bin_path = _find_emulator_bin(ctx.emulator)
    if bin_path is None:
        _log.error(
            "Emulator '%s' not installed. Expected binary at "
            "/opt/emulators/%s/%s, /userdata/emulators/%s/current/%s, "
            "or system PATH",
            ctx.emulator, ctx.emulator, ctx.emulator,
            ctx.emulator, ctx.emulator,
        )
        return 1

    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    conf = _load_hippos_conf()
    fullscreen_flags = _FULLSCREEN_FLAGS.get(ctx.emulator, [])
    cmd = [str(bin_path)] + fullscreen_flags + [str(ctx.rom)]
    _log.info("Launching standalone: %s", ' '.join(cmd))

    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, ctx.emulator, cmd, env)
    return result.returncode
