#!/usr/bin/env python3
"""HippOS emulator launcher — routes ES game launches to the right emulator."""

from __future__ import annotations

import argparse
import configparser
import logging
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Optional

try:
    import hippos_switchres as _switchres
    _HAS_SWITCHRES = True
except ImportError:
    _HAS_SWITCHRES = False

from hippos_squashfs import mount_squashfs
from hippos_overlayfs import mount_overlayfs
from hippos_bezels import prepare_bezel
from hippos_controller_monitor import start_controller_monitor

# ── Paths ──────────────────────────────────────────────────────────────────────

from HipposPaths import HOME, SAVES  # noqa: E402

# ── Shared launcher core (constants, LaunchContext, conf/env helpers) ──────────
# Imported — not defined here — so per-emulator modules never import this file
# just to reach shared symbols. Only this module's own dispatch (GENERATORS,
# main) and any not-yet-split per-emulator code should live below.

from emulatorlauncher_shared import (
    ControllerInfo,
    ESControllerProfile,
    LaunchContext,
    _HUD_CONFIG_PATH,
    _conf_bool,
    _conf_value,
    _ensure_section,
    _get_yaml_system_options,
    _load_es_input_configs,
    _load_hippos_conf,
    _load_yaml_defaults,
    _log,
)


LINDBERGH_BUNDLE_DIR = Path('/opt/emulators/lindbergh-loader')


# Core search order: user-updated → bundled artifacts → Debian apt packages.
# find_core() also checks /opt/emulators/*/cores so package-specific libretro
# builds, such as flycast and snes9x, can be used without copying artifacts.


BUILTIN_DEFAULTS: dict[str, dict[str, str]] = {
    'snes':         {'emulator': 'libretro', 'core': 'bsnes_mercury_balanced'},
    'gba':          {'emulator': 'libretro', 'core': 'mgba'},
    'megadrive':    {'emulator': 'libretro', 'core': 'genesis_plus_gx'},
    'gb':           {'emulator': 'libretro', 'core': 'gambatte'},
    'gbc':          {'emulator': 'libretro', 'core': 'gambatte'},
    'nes':          {'emulator': 'libretro', 'core': 'nestopia'},
    'n64':          {'emulator': 'libretro', 'core': 'mupen64plus_next'},
    'psx':          {'emulator': 'libretro', 'core': 'pcsx_rearmed'},
    'mastersystem': {'emulator': 'libretro', 'core': 'genesis_plus_gx'},
    'gamegear':     {'emulator': 'libretro', 'core': 'genesis_plus_gx'},
    'atari2600':    {'emulator': 'libretro', 'core': 'stella'},
    'neogeo':       {'emulator': 'libretro', 'core': 'fbneo'},
    'openbor':      {'emulator': 'openbor', 'core': 'openbor6412'},
    'xbox':         {'emulator': 'xemu', 'core': 'xemu'},
    'chihiro':      {'emulator': 'xemu', 'core': 'xemu'},
    'ps3':          {'emulator': 'rpcs3', 'core': 'rpcs3'},
}


# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='[emulatorlauncher] %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)],
)

def _apply_yaml_options(conf: dict[str, str], system: str) -> None:
    """Inject YAML system options into conf as {system}.KEY (user conf wins)."""
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
    """Resolve a path that sits under a mergerfs mount to its real branch path.

    mergerfs presents a unified view across multiple branches. Some emulators
    need the actual physical path (e.g. to resolve symlinks or use inotify).
    Reads /proc/mounts, finds the matching fuse.mergerfs entry, then walks the
    colon-separated branch list until it finds one where the path exists.
    """
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


def _lindbergh_apply_mapping(
    parser: configparser.ConfigParser,
    section: str,
    mapping: dict[str, str],
    profile: ESControllerProfile,
    ctrl: ControllerInfo,
    player_index: int,
) -> None:
    _ensure_section(parser, section)
    for logical_name, button_name in mapping.items():
        source_name = logical_name
        if source_name not in profile.inputs:
            if logical_name == 'joystick1right' and 'joystick1left' in profile.inputs:
                source_name = 'joystick1left'
            elif logical_name == 'joystick1down' and 'joystick1up' in profile.inputs:
                source_name = 'joystick1up'
            elif logical_name == 'joystick2right' and 'joystick2left' in profile.inputs:
                source_name = 'joystick2left'
            elif logical_name == 'joystick2down' and 'joystick2up' in profile.inputs:
                source_name = 'joystick2up'
        binding = profile.inputs.get(source_name)
        if binding is None:
            continue

        value = _lindbergh_binding_to_value(binding, profile, logical_name)
        if value is None:
            continue

        target = button_name
        player_for_target = player_index
        if target.endswith('_ON_PLAYER_2'):
            target = target[:-12]
            player_for_target = 2
        if target == 'COIN' and player_index > 1:
            continue

        if target.startswith('ANALOGUE_'):
            if player_index == 1:
                parser.set(section, target, value)
            continue
        if target in {'TEST_BUTTON', 'PLAYER_1_BUTTON_SERVICE'}:
            parser.set(section, target, value)
            continue
        parser.set(section, f'PLAYER_{player_for_target}_{target}', value)


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
        gsname    = rom.name.replace('=', '').replace('#', '')
        folder_em = conf.get(f'{system}.folder["{rom.parent}"].emulator') or None
        folder_co = conf.get(f'{system}.folder["{rom.parent}"].core')     or None
        game_em   = conf.get(f'{system}["{gsname}"].emulator') or None
        game_co   = conf.get(f'{system}["{gsname}"].core')     or None

    defaults = _load_yaml_defaults()
    sys_def  = defaults.get(system) or BUILTIN_DEFAULTS.get(system) or {}

    # Resolution order: CLI > game > folder > system > global > defaults
    emulator = forced_emulator or game_em or folder_em or user_em or global_em or sys_def.get('emulator') or 'libretro'
    core     = forced_core     or game_co or folder_co or user_co or global_co or sys_def.get('core')     or ''
    return emulator, core


# ── Emulator binary lookup ─────────────────────────────────────────────────────


# ── Libretro device types ─────────────────────────────────────────────────────

# Maps libretro core name → device ID for P1 (default joypad = 1)
# Maps system name → device ID (fallback when core has no entry)
# Systems with complex per-player config — handled inline


# ── Netplay ────────────────────────────────────────────────────────────────────


# ── Per-system input remapping ─────────────────────────────────────────────────


# Systems incompatible with rewind (too slow or causes crashes)

# Systems incompatible with run-ahead (too demanding or causes issues)

# Cores that require .slang shaders (Vulkan-only pipeline)

# ── RetroArch controller binding tables ────────────────────────────────────────

# ES input name → RetroArch button/trigger suffix


# ES joystick axis name → RetroArch axis base name
# The ES name represents the negative/primary direction; we derive both ± from it.

# SDL hat bitmask → RetroArch direction string


# ES button names for lightgun mapping


# ── RetroArch config generator ─────────────────────────────────────────────────


# ── Video mode helpers ─────────────────────────────────────────────────────────

def _switch_video_mode(conf: dict[str, str], system: str) -> str:
    """Switch to per-game video mode. Returns previous mode string for restore."""
    original = subprocess.run(
        ['hippos-resolution', 'currentMode'],
        capture_output=True, text=True, check=False,
    ).stdout.strip()

    videomode = conf.get(f'{system}.videomode') or conf.get('crt.videomode', '') or conf.get('global.videomode', '')

    if _HAS_SWITCHRES and _switchres.is_available():
        # CRT active — use libswitchres.so directly to avoid XranR stale-mode accumulation.
        if videomode and videomode != 'default':
            parsed = _switchres.parse_videomode(videomode)
            if parsed:
                _log.info("videomode: CRT ctypes %s for '%s'", videomode, system)
                if _switchres.switch_to_mode(*parsed):
                    return original
                _log.warning("videomode: ctypes failed, falling back to subprocess")
        else:
            # No per-system mode — restore to boot resolution (already there on session start).
            boot_res = conf.get('crt.boot_resolution', '640x480i')
            parsed = _switchres.parse_videomode(boot_res)
            if parsed:
                _switchres.switch_to_mode(*parsed)
            return original

    if videomode and videomode != 'default':
        _log.info("videomode: setting '%s' for system '%s'", videomode, system)
        subprocess.run(
            ['hippos-resolution', 'setMode', videomode],
            check=False, stderr=subprocess.DEVNULL,
        )
    else:
        # Reduce 4K → ≤1080p; no-op if already within range.
        subprocess.run(
            ['hippos-resolution', 'minTomaxResolution'],
            check=False, stderr=subprocess.DEVNULL,
        )

    return original


def _prepare_ctx_bezel(ctx: LaunchContext, conf: dict[str, str]) -> None:
    """Resolve, resize, and stage bezel for this launch. Sets ctx.bezel."""
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


def _restore_video_mode(original_mode: str, conf: dict[str, str] | None = None) -> None:
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
        ['hippos-resolution', 'setMode', original_mode],
        check=False, stderr=subprocess.DEVNULL,
    )


# ── Game environment builder ───────────────────────────────────────────────────


# ── MangoHUD config generator ─────────────────────────────────────────────────

_USER_HUD_CONFIG = HOME / 'hud.config'

# Emulators that cannot use DLSYM injection — need `mangohud` prepended to cmd.


def _build_hud_config(conf: dict[str, str], ctx: LaunchContext) -> Optional[Path]:
    """Generate /var/run/hippos/hud.config. Returns path or None if HUD disabled."""
    mode = conf.get('global.hud', 'none').strip()
    if not mode or mode == 'none':
        return None
    if conf.get(f'{ctx.system}.hud_support') == 'false':
        return None

    lines: list[str] = []

    # Bezel background — must come first
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
        # Try to read a nicer name from gameinfoxml
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
        # Thumbnail: check ES scraped image path convention
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


# ── Power mode hooks ──────────────────────────────────────────────────────────

def _battery_discharging() -> bool:
    for bat in Path('/sys/class/power_supply').glob('*BAT*'):
        status_file = bat / 'status'
        try:
            if status_file.exists() and status_file.read_text(encoding='utf-8').strip() == 'Discharging':
                return True
        except OSError:
            continue
    for bat in Path('/sys/class/power_supply').glob('*bat*'):
        status_file = bat / 'status'
        try:
            if status_file.exists() and status_file.read_text(encoding='utf-8').strip() == 'Discharging':
                return True
        except OSError:
            continue
    return False


def _available_governors() -> set[str]:
    available = set()
    candidate = Path('/sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors')
    try:
        if candidate.exists():
            available.update(candidate.read_text(encoding='utf-8').split())
    except OSError:
        pass
    return available


def _current_governor() -> str:
    candidate = Path('/sys/devices/system/cpu/cpufreq/policy0/scaling_governor')
    try:
        if candidate.exists():
            return candidate.read_text(encoding='utf-8').strip()
    except OSError:
        pass
    return ''


def _set_governor(governor: str) -> bool:
    gov = governor.strip()
    if not gov:
        return False
    available = _available_governors()
    if available and gov not in available:
        _log.info("Power mode governor '%s' not available (have: %s)", gov, ', '.join(sorted(available)))
        return False

    changed = False
    for gov_file in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor'):
        try:
            gov_file.write_text(gov, encoding='utf-8')
            changed = True
        except OSError:
            continue
    if changed:
        _log.info("Applied CPU governor: %s", gov)
    return changed


def _power_mode_to_governor(mode: str) -> str:
    normalized = mode.strip().lower()
    if not normalized or normalized == 'default':
        return ''
    if normalized in ('ac', 'performance', 'highperformance', 'high_performance'):
        return 'performance'
    if normalized in ('balanced', 'balance'):
        return 'schedutil'
    if normalized in ('battery', 'powersaver', 'power_saver', 'saver'):
        return 'powersave'
    return normalized


def _apply_game_power_mode(conf: dict[str, str], system: str, rom: Path) -> str:
    previous = _current_governor()
    if not system:
        return previous

    game_name = rom.stem
    keys = []
    if game_name:
        keys.append(f'{system}["{game_name}"].powermode')
    keys.append(f'{system}.powermode')
    keys.append('global.batterymode' if _battery_discharging() else 'global.powermode')

    selected = ''
    for key in keys:
        value = _conf_value(conf, key, '')
        if value:
            selected = value
            break

    governor = _power_mode_to_governor(selected)
    if governor:
        _set_governor(governor)
    return previous


def _restore_game_power_mode(previous: str) -> None:
    if previous:
        _set_governor(previous)


# ── Generators ─────────────────────────────────────────────────────────────────


from emulatorlauncher_generic import (
    launch_libretro as _launch_libretro,
    launch_standalone as _launch_standalone,
)
from emulatorlauncher_ports import (
    launch_eduke32 as _launch_eduke32,
    launch_theforceengine as _launch_theforceengine,
    launch_tr2x as _launch_tr2x,
    launch_sonic_mania as _launch_sonic_mania,
    launch_sonicretro as _launch_sonicretro,
    launch_sonic3air as _launch_sonic3air,
    launch_catacombgl as _launch_catacombgl,
    launch_fallout1_ce as _launch_fallout1_ce,
    launch_fallout2_ce as _launch_fallout2_ce,
)
from emulatorlauncher_runtime import (
    launch_amiberry as _launch_amiberry,
    launch_lindbergh_loader as _launch_lindbergh_loader,
    launch_solarus as _launch_solarus,
    launch_steam as _launch_steam,
    launch_wine as _launch_wine,
)
from emulatorlauncher_core import (
    launch_dolphin as _launch_dolphin,
    launch_duckstation as _launch_duckstation,
    launch_flycast as _launch_flycast,
    launch_mame as _launch_mame,
    launch_mupen64plus_qt as _launch_mupen64plus_qt,
)


from emulatorlauncher_gsplus import launch_gsplus as _launch_gsplus
from emulatorlauncher_misc import (
    launch_clk as _launch_clk,
    launch_flatpak as _launch_flatpak,
    launch_heroic as _launch_heroic,
    launch_ioquake3 as _launch_ioquake3,
    launch_lexaloffle as _launch_lexaloffle,
    launch_lightspark as _launch_lightspark,
    launch_pygame as _launch_pygame,
    launch_pyxel as _launch_pyxel,
    launch_ruffle as _launch_ruffle,
    launch_sh as _launch_sh,
    launch_simcoupe as _launch_simcoupe,
    launch_tsugaru as _launch_tsugaru,
    launch_uqm as _launch_uqm,
    launch_vice as _launch_vice,
    launch_x16emu as _launch_x16emu,
    launch_redream as _launch_redream,
    launch_corsixth as _launch_corsixth,
    launch_gzdoom as _launch_gzdoom,
    launch_ryujinx as _launch_ryujinx,
)
from emulatorlauncher_model2emu import launch_model2emu as _launch_model2emu
from emulatorlauncher_play import launch_play as _launch_play
from emulatorlauncher_openbor import launch_openbor as _launch_openbor
from emulatorlauncher_shadps4 import launch_shadps4 as _launch_shadps4
from emulatorlauncher_supermodel import launch_supermodel as _launch_supermodel
from emulatorlauncher_vpinball import launch_vpinball as _launch_vpinball
from emulatorlauncher_xemu import launch_xemu as _launch_xemu
from emulatorlauncher_ares import launch_ares as _launch_ares
from emulatorlauncher_xenia import launch_xenia as _launch_xenia
from emulatorlauncher_ppsspp import launch_ppsspp as _launch_ppsspp
from emulatorlauncher_melonds import launch_melonds as _launch_melonds
from emulatorlauncher_vita3k import launch_vita3k as _launch_vita3k
from emulatorlauncher_azahar import launch_azahar as _launch_azahar
from emulatorlauncher_cemu import launch_cemu as _launch_cemu
from emulatorlauncher_pcsx2 import launch_pcsx2 as _launch_pcsx2
from emulatorlauncher_rpcs3 import launch_rpcs3 as _launch_rpcs3
from emulatorlauncher_computers import (
    launch_dosbox_staging,
    launch_dosbox_x,
    launch_hatari,
    launch_scummvm,
    launch_mupen64plus,
    launch_fsuae,
    launch_openmsx,
)
from emulatorlauncher_extras import (
    launch_xenia_edge,
    launch_citron_neo,
    launch_eden,
    launch_ymir,
    launch_xroar,
    launch_easyrpg,
    launch_thextech,
    launch_hypseus_singe,
    launch_tic80,
    launch_ikemen,
    launch_bigpemu,
    launch_applewin,
    launch_demul,
    launch_sugarbox,
)


# Emulators that write saves inside the ROM directory (squashfs ports etc.).
# These get an overlayfs layer so writes persist to /userdata/saves.
WRITES_TO_ROM: frozenset[str] = frozenset({
    'sh',
    'solarus',
    'pygame',
    'pyxel',
    'thextech',
})

# Maps emulator name → generator function.
# libretro is handled specially; everything else goes through _launch_standalone
# until it gets its own generator.
GENERATORS: dict[str, Callable[[LaunchContext], int]] = {
    'libretro':    _launch_libretro,
    'retroarch':   _launch_libretro,
    'sh':          _launch_sh,
    'duckstation': _launch_duckstation,
    'pcsx2':       _launch_pcsx2,
    'dolphin':     _launch_dolphin,
    'dolphin-emu': _launch_dolphin,
    'dosbox':         launch_dosbox_staging,
    'dosbox-x':       launch_dosbox_x,
    'dosbox_staging': launch_dosbox_staging,
    'dosboxx':        launch_dosbox_x,
    'amiberry':    _launch_amiberry,
    'applewin':    launch_applewin,
    'bigpemu':     launch_bigpemu,
    'abuse':       _launch_standalone,
    'bstone':      _launch_standalone,
    'cannonball':  _launch_standalone,
    'catacombgl':  _launch_catacombgl,
    'cdogs':       _launch_standalone,
    'cgenius':     _launch_standalone,
    'corsixth':    _launch_corsixth,
    'demul':       launch_demul,
    'devilutionx': _launch_standalone,
    'dhewm3':      _launch_standalone,
    'dxx-rebirth': _launch_standalone,
    'ecwolf':      _launch_standalone,
    'eduke32':     _launch_eduke32,
    'fury':        _launch_eduke32,
    'etlegacy':    _launch_standalone,
    'fallout1-ce': _launch_fallout1_ce,
    'fallout2-ce': _launch_fallout2_ce,
    'flatpak':     _launch_flatpak,
    'heroic':      _launch_heroic,
    'clk':         _launch_clk,
    'easyrpg':     launch_easyrpg,
    'fsuae':       launch_fsuae,
    'gzdoom':      _launch_gzdoom,
    'hcl':         _launch_standalone,
    'hurrican':    _launch_standalone,
    'gsplus':      _launch_gsplus,
    'hypseus-singe': launch_hypseus_singe,
    'ikemen':      launch_ikemen,
    'iortcw':      _launch_standalone,
    'jazz2-native': _launch_standalone,
    'lightspark':  _launch_lightspark,
    'lindbergh-loader': _launch_lindbergh_loader,
    'model2emu':   _launch_model2emu,
    'moonlight':   _launch_standalone,
    'mugen':       _launch_standalone,
    'play':        _launch_play,
    'odcommander': _launch_standalone,
    'openjazz':    _launch_standalone,
    'openjk':      _launch_standalone,
    'openjkdf2':   _launch_standalone,
    'openmohaa':   _launch_standalone,
    'openbor':     _launch_openbor,
    'pyxel':       _launch_pyxel,
    'raze':        _launch_standalone,
    'pygame':      _launch_pygame,
    'ruffle':      _launch_ruffle,
    'ryujinx':     _launch_ryujinx,
    'samcoupe':    _launch_simcoupe,
    'sdlpop':      _launch_standalone,
    'solarus':     _launch_solarus,
    'sonic-mania': _launch_sonic_mania,
    'sonic2013':   _launch_sonicretro,
    'sonic3-air':  _launch_sonic3air,
    'soniccd':     _launch_sonicretro,
    'steam':       _launch_steam,
    'sugarbox':    launch_sugarbox,
    'supermodel':  _launch_supermodel,
    'taradino':    _launch_standalone,
    'theforceengine': _launch_theforceengine,
    'thextech':    launch_thextech,
    'tic80':       launch_tic80,
    'tr1x':        _launch_standalone,
    'tr2x':        _launch_tr2x,
    'tyrian':      _launch_standalone,
    'tsugaru':     _launch_tsugaru,
    'vpinball':    _launch_vpinball,
    'vkquake':     _launch_standalone,
    'vkquake2':    _launch_standalone,
    'vkquake3':    _launch_standalone,
    'wine':        _launch_wine,
    'x16emu':      _launch_x16emu,
    'xash3d_fwgs': _launch_standalone,
    'xroar':       launch_xroar,
    'ymir':        launch_ymir,
    'yquake2':     _launch_standalone,
    'fceux':       _launch_standalone,
    'hatari':      launch_hatari,
    'mame':        _launch_mame,
    'mednafen':    _launch_standalone,
    'mupen64plus': launch_mupen64plus,
    'mupen64plus-qt': _launch_mupen64plus_qt,
    'cemu':        _launch_cemu,
    'azahar':      _launch_azahar,
    'rpcs3':       _launch_rpcs3,
    'redream':     _launch_redream,
    'shadps4':     _launch_shadps4,
    'flycast':     _launch_flycast,
    'ppsspp':      _launch_ppsspp,
    'openmsx':     launch_openmsx,
    'scummvm':     launch_scummvm,
    'stella':      _launch_standalone,
    'vice':        _launch_vice,
    'vita3k':      _launch_vita3k,
    'melonds':     _launch_melonds,
    'basilisk2':   _launch_standalone,
    'desmume':     _launch_standalone,
    'nestopia':    _launch_standalone,
    'virtualjaguar': _launch_standalone,
    'xemu':        _launch_xemu,
    'ares':        _launch_ares,
    'xenia':       _launch_xenia,
    'xenia-canary': _launch_xenia,
    'xenia-edge':  launch_xenia_edge,
    'citron-neo':  launch_citron_neo,
    'eden':        launch_eden,
    'ioquake3':    _launch_ioquake3,
    'lexaloffle':  _launch_lexaloffle,
    'uqm':         _launch_uqm,
}


# ── Entry point ────────────────────────────────────────────────────────────────

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


def main() -> int:
    args = _build_parser().parse_args()

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

    _log.info("system=%s emulator=%s core=%s controllers=%d",
              ctx.system, ctx.emulator, ctx.core, len(ctx.controllers))

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

    generator = GENERATORS.get(ctx.emulator)
    if generator is None:
        _log.error("No generator registered for emulator '%s'", ctx.emulator)
        return 1

    profiles = _load_es_input_configs()
    start_controller_monitor(ctx, profiles)

    original_mode = _switch_video_mode(conf, ctx.system)
    raw_res = subprocess.run(
        ['hippos-resolution', 'currentResolution'],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    if m := re.match(r'(\d+)x(\d+)', raw_res):
        ctx.resolution = (int(m.group(1)), int(m.group(2)))
        _log.info("videomode: game resolution %dx%d", ctx.resolution[0], ctx.resolution[1])

    _prepare_ctx_bezel(ctx, conf)
    _build_hud_config(conf, ctx)

    power_governor = _apply_game_power_mode(conf, ctx.system, ctx.rom)
    try:
        return _run_with_squashfs(ctx, generator)
    finally:
        _restore_game_power_mode(power_governor)
        _restore_video_mode(original_mode, conf)
        subprocess.run(
            ['systemctl', 'start', '--no-block', 'hippos-save-sync.service'],
            check=False, capture_output=True,
        )


def _run_with_squashfs(ctx: LaunchContext, generator: Callable[[LaunchContext], int]) -> int:
    """Mount squashfs ROM if needed, apply overlayfs for saves, run generator."""
    if ctx.rom.suffix != '.squashfs':
        return generator(ctx)

    with mount_squashfs(ctx.rom) as squash_root:
        if ctx.emulator in WRITES_TO_ROM:
            saves_root = SAVES / ctx.system / ctx.rom.stem
            with mount_overlayfs(squash_root, saves_root) as overlay:
                ctx.rom = overlay
                return generator(ctx)
        else:
            ctx.rom = squash_root
            return generator(ctx)


if __name__ == '__main__':
    sys.exit(main())
