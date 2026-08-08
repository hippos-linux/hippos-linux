from __future__ import annotations

import json

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _ensure_section,
    _find_emulator_bin,
    _load_hippos_conf,
    _new_ini_parser,
    _run_game_command,
)

from HipposPaths import CONFIGS, SAVES


# ── eduke32 / fury ──────────────────────────────────────────────────────────────

def launch_eduke32(ctx: LaunchContext) -> int:
    core = ctx.core or ctx.emulator  # 'eduke32' or 'fury'
    bin_path = _find_emulator_bin(core, ctx.emulator)
    if bin_path is None:
        return 1

    cfg_dir = CONFIGS / core
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    cfg_file = cfg_dir / f'{core}.cfg'
    parser = _new_ini_parser()
    if cfg_file.exists():
        parser.read(cfg_file)
    _ensure_section(parser, 'Screen Setup')
    parser.set('Screen Setup', 'ScreenMode', '1')
    with cfg_file.open('w') as f:
        parser.write(f)

    rom = ctx.rom
    if core == 'fury':
        cmd = [str(bin_path), '-cfg', str(cfg_file), '-gamegrp', rom.name, '-j', str(rom.parent)]
    else:
        cmd = [str(bin_path), '-cfg', str(cfg_file), '-j', str(rom.parent if rom.suffix else rom)]

    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, core, cmd, env).returncode


# ── The Force Engine ─────────────────────────────────────────────────────────────

def launch_theforceengine(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('theforceengine')
    if bin_path is None:
        return 1

    cfg_dir = CONFIGS / 'theforceengine'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    cfg_file = cfg_dir / 'settings.ini'
    parser = _new_ini_parser()
    if cfg_file.exists():
        parser.read(cfg_file)
    _ensure_section(parser, 'Window')
    parser.set('Window', 'fullscreen', 'true')
    with cfg_file.open('w') as f:
        parser.write(f)

    rom = ctx.rom
    # .tfe files point to the game data directory via first line
    data_dir = str(rom.parent)
    if rom.suffix.lower() == '.tfe' and rom.is_file():
        try:
            first_line = rom.read_text(encoding='utf-8').splitlines()[0].strip()
            if first_line:
                data_dir = str(rom.parent / first_line)
        except Exception:
            pass

    cmd = [str(bin_path), '--config', str(cfg_dir), data_dir]
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'theforceengine', cmd, env).returncode


# ── TR2X (Tomb Raider II) ────────────────────────────────────────────────────────

def launch_tr2x(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('tr2x')
    if bin_path is None:
        return 1

    rom_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    rom_dir.mkdir(parents=True, exist_ok=True)
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    cfg_dir = rom_dir / 'cfg'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / 'TR2X.json5'

    data: dict = {}
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding='utf-8'))
        except Exception:
            pass
    data['is_fullscreen'] = True
    cfg_file.write_text(json.dumps(data, indent=2), encoding='utf-8')

    cmd = [str(bin_path)]
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'tr2x', cmd, env, cwd=rom_dir).returncode


# ── Sonic Mania ──────────────────────────────────────────────────────────────────

def launch_sonic_mania(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('sonic-mania')
    if bin_path is None:
        return 1

    rom_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    rom_dir.mkdir(parents=True, exist_ok=True)
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    # Sonic Mania uses a custom key=value settings file (no sections)
    cfg_file = rom_dir / 'Settings.ini'
    lines: list[str] = []
    existing: dict[str, str] = {}
    if cfg_file.exists():
        for line in cfg_file.read_text(encoding='utf-8').splitlines():
            if '=' in line:
                k, _, v = line.partition('=')
                existing[k.strip()] = v.strip()

    existing['windowed'] = 'n'
    existing['border'] = 'n'
    cfg_file.write_text(
        '\n'.join(f'{k} = {v}' for k, v in existing.items()) + '\n',
        encoding='utf-8',
    )

    cmd = [str(bin_path)]
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'sonic-mania', cmd, env, cwd=rom_dir).returncode


# ── Sonic Retro (sonic2013 / soniccd) ────────────────────────────────────────────

def launch_sonicretro(ctx: LaunchContext) -> int:
    rom_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    emu_name = 'soniccd' if rom_dir.name.lower().endswith('.scd') else 'sonic2013'
    bin_path = _find_emulator_bin(emu_name)
    if bin_path is None:
        return 1

    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    cfg_file = rom_dir / 'settings.ini'
    parser = _new_ini_parser()
    if cfg_file.exists():
        parser.read(cfg_file)
    _ensure_section(parser, 'Window')
    parser.set('Window', 'FullScreen', 'true')
    with cfg_file.open('w') as f:
        parser.write(f)

    cmd = [str(bin_path)]
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, emu_name, cmd, env, cwd=rom_dir).returncode


# ── Sonic 3 A.I.R. ───────────────────────────────────────────────────────────────

def launch_sonic3air(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('sonic3-air')
    if bin_path is None:
        return 1

    cfg_dir = CONFIGS / 'Sonic3AIR'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    saves_dir = SAVES / 'sonic3-air'
    saves_dir.mkdir(parents=True, exist_ok=True)

    settings_file = cfg_dir / 'settings.json'
    data: dict = {}
    if settings_file.exists():
        try:
            data = json.loads(settings_file.read_text(encoding='utf-8'))
        except Exception:
            pass
    data['Fullscreen'] = 1
    settings_file.write_text(json.dumps(data, indent=2), encoding='utf-8')

    rom = ctx.rom
    cmd = [str(bin_path), '--data', str(rom)]
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'sonic3-air', cmd, env).returncode


# ── CatacombGL ───────────────────────────────────────────────────────────────────

def launch_catacombgl(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('catacombgl', 'CatacombGL')
    if bin_path is None:
        return 1

    cfg_dir = CONFIGS / 'CatacombGL'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    saves_dir = SAVES / 'CatacombGL'
    saves_dir.mkdir(parents=True, exist_ok=True)

    cfg_file = cfg_dir / 'CatacombGL.ini'
    # Flat key=value format (no section headers)
    existing: dict[str, str] = {}
    if cfg_file.exists():
        for line in cfg_file.read_text(encoding='utf-8').splitlines():
            if '=' in line:
                k, _, v = line.partition('=')
                existing[k.strip()] = v.strip()
    existing['screenmode'] = 'fullscreen'
    cfg_file.write_text(
        '\n'.join(f'{k}={v}' for k, v in existing.items()) + '\n',
        encoding='utf-8',
    )

    cmd = [str(bin_path), '--savedir', str(saves_dir)]
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'catacombgl', cmd, env, cwd=ctx.rom.parent if ctx.rom.is_file() else ctx.rom).returncode


# ── Fallout 1 CE ─────────────────────────────────────────────────────────────────

def launch_fallout1_ce(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('fallout1-ce')
    if bin_path is None:
        return 1

    rom_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    cfg_file = rom_dir / 'fallout.cfg'
    parser = _new_ini_parser()
    if cfg_file.exists():
        parser.read(cfg_file)
    _ensure_section(parser, 'MAIN')
    parser.set('MAIN', 'WINDOWED', '0')
    with cfg_file.open('w') as f:
        parser.write(f)

    cmd = [str(bin_path)]
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'fallout1-ce', cmd, env, cwd=rom_dir).returncode


# ── Fallout 2 CE ─────────────────────────────────────────────────────────────────

def launch_fallout2_ce(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('fallout2-ce')
    if bin_path is None:
        return 1

    rom_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    cfg_file = rom_dir / 'fallout2.cfg'
    parser = _new_ini_parser()
    if cfg_file.exists():
        parser.read(cfg_file)
    _ensure_section(parser, 'MAIN')
    parser.set('MAIN', 'WINDOWED', '0')
    with cfg_file.open('w') as f:
        parser.write(f)

    cmd = [str(bin_path)]
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'fallout2-ce', cmd, env, cwd=rom_dir).returncode
