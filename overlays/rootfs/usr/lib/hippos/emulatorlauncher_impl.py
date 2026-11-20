#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import subprocess
import signal
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator, Optional

try:
    import hippos_switchres as _switchres
    _HAS_SWITCHRES = True
except ImportError:
    _HAS_SWITCHRES = False

from hippos_squashfs import mount_squashfs
from hippos_overlayfs import mount_overlayfs
from hippos_bezels import prepare_bezel
from hippos_controller_monitor import start_controller_monitor

from HipposPaths import HOME, SAVES_RW

from emulatorlauncher_shared import (
    ControllerInfo,
    ESControllerProfile,
    LaunchContext,
    EmulatorNotInstalled,
    _HUD_CONFIG_PATH,
    _conf_bool,
    _get_yaml_system_options,
    game_config_name,
    _load_es_input_configs,
    _load_hippos_conf,
    _load_yaml_defaults,
    _log,
    LAUNCHER_STARTED,
    launch_clock,
    launch_step,
)
from emulatorlauncher_power import game_power_settings
from emulatorlauncher_async import Parallel, in_thread, timed

LINDBERGH_BUNDLE_DIR = Path('/opt/emulators/linuxloader')

LAUNCH_ERROR_FILE = Path('/tmp/launch_error.log')
EXIT_UNKNOWN_EMULATOR = 203
EXIT_LAUNCH_FAILED = 250

logging.basicConfig(
    level=logging.INFO,
    format='[emulatorlauncher] %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)],
)

def _apply_yaml_options(conf: dict[str, str], system: str) -> None:
    for key, value in _get_yaml_system_options(system).items():
        if key == 'forceNoBezel':
            conf_key = f'{system}.bezel'
            conf_val = 'none' if value else ''
        elif isinstance(value, bool):
            conf_key = f'{system}.{key}'
            conf_val = 'true' if value else 'false'
        else:
            conf_key = f'{system}.{key}'
            conf_val = str(value)
        if conf_key not in conf:
            conf[conf_key] = conf_val

def _load_game_wheel_metadata(gameinfoxml: Optional[Path]) -> dict[str, str]:
    if gameinfoxml is None or not gameinfoxml.exists():
        return {}
    try:
        root = ET.parse(gameinfoxml).getroot()
    except ET.ParseError as exc:
        _log.warning("Could not parse %s: %s", gameinfoxml, exc)
        return {}
    wheel = root.find('.//wheel')
    if wheel is None:
        return {}
    data = {k: v for k, v in wheel.attrib.items() if v}
    if 'wheel' not in data:
        data['wheel'] = 'joystick1left'
    return data

def _load_game_gun_metadata(gameinfoxml: Optional[Path]) -> dict[str, str]:
    if gameinfoxml is None or not gameinfoxml.exists():
        return {}
    try:
        root = ET.parse(gameinfoxml).getroot()
    except ET.ParseError as exc:
        _log.warning("Could not parse %s: %s", gameinfoxml, exc)
        return {}

    gun = root.find('.//gun')
    if gun is None:
        return {}
    data = {k: v for k, v in gun.attrib.items() if v}
    if 'type' not in data and 'gun_type' in data:
        data['type'] = data['gun_type']
    return data

def _resolve_mergerfs_path(path: Path) -> Path:
    try:
        path_str = str(path)
        with open('/proc/mounts') as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3 or parts[2] != 'fuse.mergerfs':
                    continue
                mount_point = parts[1]
                if not (path_str.startswith(mount_point + '/') or path_str == mount_point):
                    continue
                relative = path_str[len(mount_point):]
                for branch in parts[0].split(':'):
                    branch = branch.strip()
                    if not branch:
                        continue
                    if not branch.startswith('/'):
                        branch = '/' + branch
                    candidate = Path(branch.rstrip('/') + relative)
                    if candidate.exists():
                        _log.debug("mergerfs: resolved %s -> %s", path, candidate)
                        return candidate
    except Exception as exc:
        _log.debug("mergerfs path resolution failed: %s", exc)
    return path

def resolve_emulator_core(
    system: str,
    forced_emulator: Optional[str],
    forced_core: Optional[str],
    rom: Optional[Path] = None,
) -> tuple[str, str]:
    conf = _load_hippos_conf()

    global_em  = conf.get('global.emulator') or None
    global_co  = conf.get('global.core')     or None

    user_em    = conf.get(f'{system}.emulator') or None
    user_co    = conf.get(f'{system}.core')     or None

    folder_em = folder_co = None
    game_em   = game_co   = None
    if rom is not None:
        gsname    = game_config_name(rom)
        folder_em = conf.get(f'{system}.folder["{rom.parent}"].emulator') or None
        folder_co = conf.get(f'{system}.folder["{rom.parent}"].core')     or None
        game_em   = conf.get(f'{system}["{gsname}"].emulator') or None
        game_co   = conf.get(f'{system}["{gsname}"].core')     or None

    defaults = _load_yaml_defaults()
    sys_def  = defaults.get(system) or {}

    chosen_em = forced_emulator or game_em or folder_em or user_em or global_em
    emulator = chosen_em or sys_def.get('emulator') or 'libretro'
    core     = forced_core or game_co or folder_co or user_co or global_co or sys_def.get('core') or ''
    if chosen_em is None and rom is not None:
        emulator, core = _compatible_default(sys_def, emulator, core, rom)
    return emulator, core

def _compatible_default(sys_def: dict, emulator: str, core: str, rom: Path) -> tuple[str, str]:
    ext = rom.suffix.lower()
    candidates = sys_def.get('candidates') or []
    if not any(c['emulator'] == emulator and ext in c.get('exclude_extensions', ()) for c in candidates):
        return emulator, core
    for candidate in candidates:
        if ext not in candidate.get('exclude_extensions', ()):
            _log.info("%s can't run %s files; using %s/%s", emulator, ext, candidate['emulator'], candidate['core'])
            return candidate['emulator'], candidate['core']
    return emulator, core

def _game_output() -> str:
    return subprocess.run(
        ['hippos-resolution', 'currentOutput'],
        capture_output=True, text=True, check=False,
    ).stdout.strip()

def _switch_video_mode(conf: dict[str, str], system: str) -> tuple[str, str]:
    output = _game_output()
    original = subprocess.run(
        ['hippos-resolution', '--screen', output, 'currentMode'],
        capture_output=True, text=True, check=False,
    ).stdout.strip()

    videomode = conf.get(f'{system}.videomode') or conf.get('crt.videomode', '') or conf.get('global.videomode', '')

    if _HAS_SWITCHRES and _switchres.is_available():
        if videomode and videomode != 'default':
            parsed = _switchres.parse_videomode(videomode)
            if parsed:
                _log.info("videomode: CRT ctypes %s for '%s'", videomode, system)
                if _switchres.switch_to_mode(*parsed):
                    return output, original
                _log.warning("videomode: ctypes failed, falling back to subprocess")
        else:
            boot_res = conf.get('crt.boot_resolution', '640x480i')
            parsed = _switchres.parse_videomode(boot_res)
            if parsed:
                _switchres.switch_to_mode(*parsed)
            return output, original

    if videomode and videomode != 'default':
        _log.info("videomode: setting '%s' for system '%s'", videomode, system)
        subprocess.run(
            ['hippos-resolution', '--screen', output, 'applyMode', videomode],
            check=False, stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(
            ['hippos-resolution', '--screen', output, 'minTomaxResolution'],
            check=False, stderr=subprocess.DEVNULL,
        )

    return output, original

def _prepare_ctx_bezel(ctx: LaunchContext, conf: dict[str, str]) -> None:
    from hippos_bezels import generate_gun_help, gun_border_color
    if ctx.resolution is None:
        return
    sys_bezel  = conf.get(f'{ctx.system}.bezel')
    bezel_name = sys_bezel if sys_bezel is not None else conf.get('global.bezel', '')
    if not bezel_name or bezel_name == 'none':
        generate_gun_help(ctx.system, ctx.rom, ctx.lightgun, ctx.game_gun, ctx.resolution)
        return
    stretch       = _conf_bool(conf, 'global.bezel_stretch')
    tattoo_type   = conf.get('global.bezel.tattoo', 'none')
    tattoo_file   = conf.get('global.bezel.tattoo_file')
    tattoo_corner = conf.get('global.bezel.tattoo_corner', 'NW')
    tattoo_resize = _conf_bool(conf, 'global.bezel.resize_tattoo', True)
    gun_border    = conf.get('global.use_guns') and conf.get('global.guns_borders_size', 'none') or 'none'
    gun_aspect    = conf.get('global.ratio')
    gun_col       = gun_border_color(conf)
    ra_game_id    = ctx.game_gun.get('ra_id') if ctx.lightgun else None
    qr_corner     = conf.get('global.bezel.qrcode_corner', 'NE')
    ctx.bezel = prepare_bezel(
        rom=ctx.rom,
        system=ctx.system,
        emulator=ctx.emulator,
        bezel_name=bezel_name,
        resolution=ctx.resolution,
        stretch=stretch,
        tattoo_type=tattoo_type,
        tattoo_file=tattoo_file,
        tattoo_corner=tattoo_corner,
        tattoo_resize=tattoo_resize,
        gun_border=gun_border,
        gun_aspect_ratio=gun_aspect,
        gun_border_col=gun_col,
        ra_game_id=ra_game_id,
        qr_corner=qr_corner,
    )
    generate_gun_help(ctx.system, ctx.rom, ctx.lightgun, ctx.game_gun, ctx.resolution)

def _restore_video_mode(output: str, original_mode: str, conf: dict[str, str] | None = None) -> None:
    if not original_mode:
        return
    _log.info("videomode: restoring '%s'", original_mode)
    if _HAS_SWITCHRES and _switchres.is_available():
        boot_res = (conf or {}).get('crt.boot_resolution', '640x480i')
        parsed   = _switchres.parse_videomode(boot_res)
        if parsed and _switchres.switch_to_mode(*parsed):
            return
        _log.warning("videomode: ctypes restore failed, falling back to subprocess")
    subprocess.run(
        ['hippos-resolution', '--screen', output, 'applyMode', original_mode],
        check=False, stderr=subprocess.DEVNULL,
    )

_USER_HUD_CONFIG = HOME / 'hud.config'

def _build_hud_config(conf: dict[str, str], ctx: LaunchContext) -> Optional[Path]:
    mode = conf.get('global.hud', 'none').strip()
    if not mode or mode == 'none':
        return None
    if conf.get(f'{ctx.system}.hud_support') == 'false':
        return None

    lines: list[str] = []

    if ctx.bezel is not None:
        lines.append(f'background_image={ctx.bezel}')
        lines.append('legacy_layout=false')

    if mode == 'perf':
        lines += [
            'fps',
            'frametime',
            'cpu_temp',
            'gpu_temp',
            'cpu_load',
            'gpu_load',
            'vram',
            'ram',
        ]
    elif mode == 'game':
        game_name = ctx.rom.stem
        if ctx.gameinfoxml and ctx.gameinfoxml.exists():
            try:
                root = ET.parse(ctx.gameinfoxml).getroot()
                name_el = root.find('.//name')
                if name_el is not None and name_el.text:
                    game_name = name_el.text.strip()
            except ET.ParseError:
                pass
        lines += [
            'fps',
            f'custom_text={game_name}',
            f'custom_text={ctx.system}',
            f'custom_text={ctx.emulator}/{ctx.core}' if ctx.core else f'custom_text={ctx.emulator}',
        ]
        thumb = ctx.rom.with_suffix('.png')
        if not thumb.exists():
            thumb = ctx.rom.parent / 'images' / f'{ctx.rom.stem}.png'
        if thumb.exists():
            lines.append(f'image={thumb}')
    elif mode == 'custom':
        if _USER_HUD_CONFIG.exists():
            lines += _USER_HUD_CONFIG.read_text().splitlines()
        else:
            _log.warning("hud: custom mode but %s not found, using perf", _USER_HUD_CONFIG)
            lines += ['fps', 'frametime', 'cpu_load', 'gpu_load']

    position = conf.get('global.hud_corner', 'top-left')
    lines.append(f'position={position}')

    _HUD_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HUD_CONFIG_PATH.write_text('\n'.join(lines) + '\n')
    _log.info("hud: config written (%s mode, %s)", mode, position)
    return _HUD_CONFIG_PATH

import emulatorlauncher_86box
import emulatorlauncher_ares
import emulatorlauncher_azahar
import emulatorlauncher_cemu
import emulatorlauncher_computers
import emulatorlauncher_core
import emulatorlauncher_drastic
import emulatorlauncher_extras
import emulatorlauncher_generic
import emulatorlauncher_gopher64
import emulatorlauncher_gsplus
import emulatorlauncher_lunaria
import emulatorlauncher_melonds
import emulatorlauncher_mesen2
import emulatorlauncher_misc
import emulatorlauncher_model2emu
import emulatorlauncher_openbor
import emulatorlauncher_pcsx2
import emulatorlauncher_play
import emulatorlauncher_ports
import emulatorlauncher_ppsspp
import emulatorlauncher_rpcs3
import emulatorlauncher_runtime
import emulatorlauncher_shadps4
import emulatorlauncher_sheepshaver
import emulatorlauncher_stella
import emulatorlauncher_supermodel
import emulatorlauncher_vita3k
import emulatorlauncher_vpinball
import emulatorlauncher_waydroid
import emulatorlauncher_windowsarcadeloader
import emulatorlauncher_xbased
import emulatorlauncher_xemu
import emulatorlauncher_xenia

from emulatorlauncher_registry import Emulator, lookup

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='HippOS emulator launcher')

    for n in range(1, 9):
        p.add_argument(f'-p{n}index',      type=int, required=False)
        p.add_argument(f'-p{n}guid',       type=str, required=False)
        p.add_argument(f'-p{n}name',       type=str, required=False)
        p.add_argument(f'-p{n}devicepath', type=str, required=False)
        p.add_argument(f'-p{n}iswheel',    type=int, required=False)
        p.add_argument(f'-p{n}wheelrotationangle', type=int, required=False)
        p.add_argument(f'-p{n}nbbuttons',  type=int, required=False)
        p.add_argument(f'-p{n}nbhats',     type=int, required=False)
        p.add_argument(f'-p{n}nbaxes',     type=int, required=False)

    p.add_argument('-system',       type=str,  required=True)
    p.add_argument('-rom',          type=Path, required=True)
    p.add_argument('-emulator',     type=str,  required=False)
    p.add_argument('-core',         type=str,  required=False)
    p.add_argument('-systemname',   type=str,  required=False)
    p.add_argument('-monitor',      type=int,  required=False)
    p.add_argument('-gameinfoxml',  type=str,  required=False, nargs='?', default=None, const=None)
    p.add_argument('-netplaymode',  type=str,  required=False)
    p.add_argument('-netplayip',    type=str,  required=False)
    p.add_argument('-netplayport',  type=str,  required=False)
    p.add_argument('-state_slot',   type=str,  required=False)
    p.add_argument('-state_filename', type=str, required=False)
    p.add_argument('-autosave',     type=str,  required=False)
    p.add_argument('-lightgun',     action='store_true')
    p.add_argument('-wheel',        action='store_true')
    return p

def _build_controllers(args: argparse.Namespace) -> list[ControllerInfo]:
    controllers = []
    for n in range(1, 9):
        idx = getattr(args, f'p{n}index', None)
        if idx is None:
            continue
        controllers.append(ControllerInfo(
            player=n,
            index=idx,
            guid=getattr(args, f'p{n}guid',       None) or '',
            name=getattr(args, f'p{n}name',       None) or '',
            device_path=getattr(args, f'p{n}devicepath', None) or '',
            is_wheel=bool(int(getattr(args, f'p{n}iswheel', 0) or 0)),
            wheel_rotation_angle=getattr(args, f'p{n}wheelrotationangle', None) or 0,
            nb_buttons=getattr(args, f'p{n}nbbuttons',  None) or 0,
            nb_hats=getattr(args, f'p{n}nbhats',     None) or 0,
            nb_axes=getattr(args, f'p{n}nbaxes',     None) or 0,
        ))
    return controllers

class _LastError(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.message = ''

    def emit(self, record: logging.LogRecord) -> None:
        self.message = record.getMessage()


def main() -> int:
    _log.info("launch: imports %.2fs", time.perf_counter() - LAUNCHER_STARTED)
    last_error = _LastError()
    logging.getLogger().addHandler(last_error)
    try:
        code = _launch(_build_parser().parse_args())
    except EmulatorNotInstalled as exc:
        _log.error("%s", exc)
        code = 1
    except Exception as exc:
        _log.exception("Launch failed: %s", exc)
        code = 1
    if code in (-signal.SIGTERM, -signal.SIGKILL):
        _log.info("launch: game stopped by signal %d", -code)
        code = 0
    if code != 0 and launch_clock.game_started is None and not 200 <= code <= 300:
        LAUNCH_ERROR_FILE.write_text(last_error.message or 'The game could not be started.', encoding='utf-8')
        code = EXIT_LAUNCH_FAILED
    if launch_clock.game_ended is not None:
        _log.info("launch: teardown %.2fs", time.perf_counter() - launch_clock.game_ended)
    return code


def _launch(args: argparse.Namespace) -> int:

    emulator, core = resolve_emulator_core(args.system, args.emulator, args.core, args.rom)
    controllers    = _build_controllers(args)

    ctx = LaunchContext(
        system=args.system,
        rom=args.rom,
        emulator=emulator,
        core=core,
        gameinfoxml=Path(args.gameinfoxml) if args.gameinfoxml and args.gameinfoxml != '/dev/null' else None,
        lightgun=args.lightgun,
        wheel=args.wheel,
        controllers=controllers,
    )
    ctx.rom         = _resolve_mergerfs_path(ctx.rom)
    ctx.game_wheel  = _load_game_wheel_metadata(ctx.gameinfoxml)
    ctx.game_gun    = _load_game_gun_metadata(ctx.gameinfoxml)
    ctx.netplay_mode = getattr(args, 'netplaymode', '') or ''
    ctx.netplay_ip   = getattr(args, 'netplayip',   '') or ''
    ctx.netplay_port = getattr(args, 'netplayport',  '') or ''
    ctx.monitor      = args.monitor if args.monitor is not None else -1

    _log.info("system=%s emulator=%s core=%s controllers=%d",
              ctx.system, ctx.emulator, ctx.core, len(ctx.controllers))

    with launch_step('settings'):
        conf = _load_hippos_conf()
        _apply_yaml_options(conf, ctx.system)
    if not _conf_bool(conf, 'global.use_guns', True):
        ctx.lightgun = False
    if not _conf_bool(conf, 'global.use_wheels', True):
        ctx.wheel = False

    if ctx.lightgun:
        os.environ['HIPPOS_LIGHTGUN'] = '1'
    else:
        os.environ.pop('HIPPOS_LIGHTGUN', None)
    if ctx.wheel:
        os.environ['HIPPOS_WHEEL'] = '1'
        for ctrl in ctx.controllers:
            if ctrl.is_wheel and ctrl.wheel_rotation_angle > 0:
                os.environ['HIPPOS_WHEEL_ROTATION_ANGLE'] = str(ctrl.wheel_rotation_angle)
                break
    else:
        os.environ.pop('HIPPOS_WHEEL', None)
        os.environ.pop('HIPPOS_WHEEL_ROTATION_ANGLE', None)

    emulator = lookup(ctx.emulator)
    if emulator is None:
        _log.error("No launcher registered for emulator '%s'", ctx.emulator)
        return EXIT_UNKNOWN_EMULATOR

    return asyncio.run(_prepare_and_run(ctx, conf, emulator))

async def _prepare_and_run(ctx: LaunchContext, conf: dict[str, str], emulator: Emulator) -> int:
    async with AsyncExitStack() as stack:
        stack.callback(_start_save_sync)
        *_, rom = await stack.enter_async_context(Parallel(
            timed('controllers', _controllers(ctx)),
            timed('display', _display(conf, ctx)),
            timed('hud', _hud(conf, ctx)),
            timed('power', in_thread(game_power_settings(conf, ctx.system, ctx.rom))),
            timed('rom', _prepared_rom(ctx, emulator)),
        ))
        ctx.rom = rom
        return await asyncio.to_thread(emulator.launch, ctx)

@asynccontextmanager
async def _controllers(ctx: LaunchContext) -> AsyncIterator[None]:
    profiles = await asyncio.to_thread(_load_es_input_configs)
    start_controller_monitor(ctx, profiles)
    yield

@asynccontextmanager
async def _display(conf: dict[str, str], ctx: LaunchContext) -> AsyncIterator[None]:
    game_output, original_mode = await asyncio.to_thread(_switch_video_mode, conf, ctx.system)
    try:
        resolution = await asyncio.to_thread(
            subprocess.run, ['hippos-resolution', '--screen', game_output, 'currentResolution'],
            capture_output=True, text=True, check=False,
        )
        if m := re.match(r'(\d+)x(\d+)', resolution.stdout.strip()):
            ctx.resolution = (int(m.group(1)), int(m.group(2)))
            _log.info("videomode: game resolution %dx%d", ctx.resolution[0], ctx.resolution[1])
        with launch_step('bezel'):
            await asyncio.to_thread(_prepare_ctx_bezel, ctx, conf)
        yield
    finally:
        await asyncio.to_thread(_restore_video_mode, game_output, original_mode, conf)

@asynccontextmanager
async def _hud(conf: dict[str, str], ctx: LaunchContext) -> AsyncIterator[None]:
    await asyncio.to_thread(_build_hud_config, conf, ctx)
    yield

@asynccontextmanager
async def _prepared_rom(ctx: LaunchContext, emulator: Emulator) -> AsyncIterator[Path]:
    if ctx.rom.suffix != '.squashfs':
        yield ctx.rom
        return
    async with in_thread(mount_squashfs(ctx.rom)) as squash_root:
        if emulator.writes_to_rom:
            async with in_thread(mount_overlayfs(squash_root, SAVES_RW / ctx.system / ctx.rom.stem)) as overlay:
                yield overlay
        else:
            yield squash_root

def _start_save_sync() -> None:
    subprocess.run(
        ['systemctl', 'start', '--no-block', 'hippos-save-sync.service'],
        check=False, capture_output=True,
    )

if __name__ == '__main__':
    sys.exit(main())
