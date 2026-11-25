from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _ensure_section,
    _game_value,
    _load_effective_hippos_conf,
    _load_es_input_configs,
    _load_hippos_conf,
    _new_ini_parser,
    _pick_es_profile,
    _run_game_command,
    _require_emulator_bin,
)

from HipposPaths import CONFIGS, ROMS, SAVES
from emulatorlauncher_registry import Emulator, register

def launch_eduke32(ctx: LaunchContext) -> int:
    core = ctx.core or ctx.emulator
    bin_path = _require_emulator_bin(core, ctx.emulator)

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
    return _run_game_command(ctx, cmd, env).returncode

def launch_theforceengine(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('theforceengine')

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
    return _run_game_command(ctx, cmd, env).returncode

def launch_tr2x(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('tr2x')

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
    return _run_game_command(ctx, cmd, env, cwd=rom_dir).returncode

def _write_ini(path: Path, values: dict[str, dict[str, str]]) -> None:
    parser = _new_ini_parser()
    parser.read(path, encoding='utf-8')
    for section, keys in values.items():
        _ensure_section(parser, section)
        parser[section].update(keys)
    with path.open('w', encoding='utf-8') as handle:
        parser.write(handle, space_around_delimiters=False)

def _link_into(folder: Path, target: Path) -> Path:
    link = folder / target.name
    if not (link.is_symlink() and link.readlink() == target):
        link.unlink(missing_ok=True)
        link.symlink_to(target)
    return link

def launch_sonic_mania(ctx: LaunchContext) -> int:
    binary = _require_emulator_bin('sonic-mania')
    game_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    _write_ini(game_dir / 'Settings.ini', {'Video': {'windowed': 'n', 'border': 'n'}})

    mods_dir = game_dir / 'mods'
    mods_dir.mkdir(exist_ok=True)
    _link_into(mods_dir, binary.parent.parent / 'share' / 'mods' / 'GLShaders')
    _write_ini(mods_dir / 'modconfig.ini', {'Mods': {'GLShaders': 'y'}})

    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, [str(binary)], env, cwd=game_dir).returncode

def launch_sonicretro(ctx: LaunchContext) -> int:
    binary = _require_emulator_bin('soniccd' if ctx.rom.suffix.lower() == '.scd' else 'sonic2013')
    game_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    _write_ini(game_dir / 'settings.ini', {'Window': {'FullScreen': 'true'}})
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, [str(binary)], env, cwd=game_dir).returncode

SONIC3AIR_ROM = 'Sonic_Knuckles_wSonic3.bin'

def launch_sonic3air(ctx: LaunchContext) -> int:
    binary = _require_emulator_bin('sonic3-air')
    settings_file = CONFIGS / 'Sonic3AIR' / 'settings.json'
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings = json.loads(settings_file.read_text(encoding='utf-8')) if settings_file.exists() else {}
    game_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    settings['Fullscreen'] = 1
    settings['RomPath'] = str(game_dir / SONIC3AIR_ROM)
    settings_file.write_text(json.dumps(settings, indent=2), encoding='utf-8')

    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['XDG_DATA_HOME'] = str(CONFIGS)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    return _run_game_command(ctx, [str(binary)], env, cwd=binary.parent).returncode

def launch_catacombgl(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('catacombgl', 'CatacombGL')

    cfg_dir = CONFIGS / 'CatacombGL'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    saves_dir = SAVES / 'CatacombGL'
    saves_dir.mkdir(parents=True, exist_ok=True)

    cfg_file = cfg_dir / 'CatacombGL.ini'
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
    return _run_game_command(ctx, cmd, env, cwd=ctx.rom.parent if ctx.rom.is_file() else ctx.rom).returncode

FALLOUT_DEFAULT_RESOLUTION = (1280, 720)


@dataclass(frozen=True)
class FalloutGame:
    config_file: str
    resolution_file: str
    music_path: str
    data_files: dict[str, str]


FALLOUT_GAMES = {
    'fallout1-ce': FalloutGame('fallout.cfg', 'f1_res.ini', 'DATA/SOUND/MUSIC/', {
        'critter_dat': 'CRITTER.DAT', 'critter_patches': 'DATA',
        'master_dat': 'MASTER.DAT', 'master_patches': 'DATA',
    }),
    'fallout2-ce': FalloutGame('fallout2.cfg', 'f2_res.ini', 'sound/music/', {
        'critter_dat': 'critter.dat', 'critter_patches': 'data',
        'master_dat': 'master.dat', 'master_patches': 'data',
    }),
}


def _write_fallout_config(game_dir: Path, game: FalloutGame, ctx: LaunchContext, conf: dict[str, str]) -> None:
    _write_ini(game_dir / game.config_file, {
        'preferences': {
            'game_difficulty': _game_value(conf, ctx, 'fallout_game_difficulty', '1'),
            'combat_difficulty': _game_value(conf, ctx, 'fallout_combat_difficulty', '1'),
            'subtitles': _game_value(conf, ctx, 'fallout_subtitles', '0'),
        },
        'sound': {'music_path1': game.music_path, 'music_path2': game.music_path},
        'system': game.data_files,
    })
    width, height = ctx.resolution or FALLOUT_DEFAULT_RESOLUTION
    _write_ini(game_dir / game.resolution_file, {'MAIN': {
        'SCR_WIDTH': str(width),
        'SCR_HEIGHT': str(height),
        'SCALE_2X': '1' if width >= 1280 and height >= 960 else '0',
        'WINDOWED': '0',
    }})


def launch_fallout_ce(ctx: LaunchContext) -> int:
    binary = _require_emulator_bin(ctx.emulator)
    game_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    conf = _load_effective_hippos_conf()
    _write_fallout_config(game_dir, FALLOUT_GAMES[ctx.emulator], ctx, conf)
    link = _link_into(game_dir, binary)
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, [str(link)], env, cwd=game_dir).returncode


CGENIUS_SAVES = SAVES / 'cgenius'
CGENIUS_ROMS = ROMS / 'cgenius'
CGENIUS_RENDER_SIZES = {'200': ('320', '200'), '240': ('320', '240'), '360': ('640', '360'), '480': ('640', '480')}
CGENIUS_ACTIONS = {
    'a': 'Fire',
    'b': 'Jump',
    'x': 'Status',
    'y': 'Pogo',
    'pageup': 'Camlead',
    'pagedown': 'Run',
    'up': 'Up',
    'down': 'Down',
    'left': 'Left',
    'right': 'Right',
}


def _cgenius_binding(joystick: int, binding) -> str:
    if binding.type == 'hat':
        return f'Joy{joystick}-H{binding.value}'
    return f'Joy{joystick}-{binding.type[0].upper()}{binding.code}'


def _write_cgenius_config(ctx: LaunchContext, conf: dict[str, str]) -> None:
    width, height = CGENIUS_RENDER_SIZES.get(_game_value(conf, ctx, 'cgenius_render', '200'), CGENIUS_RENDER_SIZES['200'])
    values = {
        'FileHandling': {
            'EnableLogfile': 'false',
            'SearchPath1': str(CGENIUS_ROMS),
            'SearchPath2': str(CGENIUS_ROMS / 'games'),
        },
        'Video': {
            'fullscreen': 'true',
            'aspect': _game_value(conf, ctx, 'cgenius_aspect', '4:3'),
            'filter': _game_value(conf, ctx, 'cgenius_filter', '1'),
            'OGLfilter': _game_value(conf, ctx, 'cgenius_quality', 'nearest'),
            'ShowCursor': 'false',
        },
        **{engine: {'gameWidth': width, 'gameHeight': height} for engine in ('Launcher', 'Vorticon', 'Galaxy', 'Cosmos')},
    }
    profiles = _load_es_input_configs()
    for ctrl in ctx.controllers[:4]:
        if (profile := _pick_es_profile(profiles, ctrl)) is not None:
            values[f'input{ctrl.index}'] = {
                action: _cgenius_binding(ctrl.index, binding)
                for es_name, action in CGENIUS_ACTIONS.items()
                if (binding := profile.inputs.get(es_name)) is not None
            }
    _write_ini(CGENIUS_SAVES / 'cgenius.cfg', values)


def launch_cgenius(ctx: LaunchContext) -> int:
    binary = _require_emulator_bin('cgenius')
    conf = _load_effective_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    CGENIUS_SAVES.mkdir(parents=True, exist_ok=True)
    home_link = Path(env['HOME']) / '.CommanderGenius'
    if home_link.is_symlink() or not home_link.exists():
        home_link.unlink(missing_ok=True)
        home_link.symlink_to(CGENIUS_SAVES, target_is_directory=True)
    _write_cgenius_config(ctx, conf)
    game_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    system_dir = next((parent for parent in game_dir.parents if parent.name == CGENIUS_ROMS.name), None)
    if system_dir is not None:
        game_dir = game_dir.relative_to(system_dir)
    return _run_game_command(ctx, [str(binary), f'dir={game_dir}'], env, cwd=binary.parent).returncode

def launch_jazz2(ctx: LaunchContext) -> int:
    binary = _require_emulator_bin('jazz2-native')
    saves_dir = SAVES / 'jazz2'
    saves_dir.mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['XDG_DATA_HOME'] = str(ROMS)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    cmd = [str(binary), '/fullscreen', '/config', str(saves_dir / 'Jazz2.config')]
    return _run_game_command(ctx, cmd, env).returncode

def launch_openjazz(ctx: LaunchContext) -> int:
    binary = _require_emulator_bin('openjazz')
    game_dir = ctx.rom if ctx.rom.is_dir() else ctx.rom.parent
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, [str(binary), '-f', f'{game_dir}/'], env).returncode

register(Emulator('catacombgl', launch_catacombgl))
register(Emulator('eduke32', launch_eduke32))
register(Emulator('fury', launch_eduke32))
register(Emulator('cgenius', launch_cgenius, binaries=('CGeniusExe',)))
register(Emulator('fallout1-ce', launch_fallout_ce, writes_to_rom=True))
register(Emulator('fallout2-ce', launch_fallout_ce, writes_to_rom=True))
register(Emulator('jazz2-native', launch_jazz2, binaries=('jazz2',)))
register(Emulator('openjazz', launch_openjazz, binaries=('OpenJazz',)))
register(Emulator('sonic-mania', launch_sonic_mania, writes_to_rom=True))
register(Emulator('sonic2013', launch_sonicretro, writes_to_rom=True))
register(Emulator('sonic3-air', launch_sonic3air, binaries=('sonic3air_linux',)))
register(Emulator('soniccd', launch_sonicretro, writes_to_rom=True))
register(Emulator('theforceengine', launch_theforceengine))
register(Emulator('tr2x', launch_tr2x))
