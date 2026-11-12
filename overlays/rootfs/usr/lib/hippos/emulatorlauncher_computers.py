
from __future__ import annotations

import configparser
import shutil
import zipfile
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

from emulatorlauncher_shared import (
    ControllerInfo,
    LaunchContext,
    _build_game_env,
    _conf_value,
    _find_emulator_bin,
    _load_es_input_configs,
    _load_hippos_conf,
    _log,
    _pick_es_profile,
    _run_game_command,
)

from HipposPaths import BIOS, CACHE, CONFIGS, SAVES, SCREENSHOTS
import hippos_win9x

def launch_dosbox_staging(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    rom  = ctx.rom
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('dosbox-staging', 'dosbox')
    if bin_path is None:
        _log.error("dosbox-staging: binary not found")
        return 1

    cmd: list[str] = [str(bin_path), '--fullscreen']

    for cfg_name in ('dosbox.cfg', 'dosbox.conf'):
        cfg_file = rom.parent / cfg_name
        if cfg_file.exists():
            cmd += ['--conf', str(cfg_file)]
            break

    cmd += [
        '--working-dir', str(rom.parent),
        '-c', f'mount c "{rom.parent}"',
        '-c', 'c:',
    ]

    if rom.is_dir():
        bat = rom / 'dosbox.bat'
        exe = next(rom.glob('*.bat'), None) or next(rom.glob('*.exe'), None)
        cmd += ['-c', str(bat.name if bat.exists() else (exe.name if exe else 'dosbox.bat'))]
    else:
        cmd += ['-c', str(rom.name)]

    cmd.append('--exit')

    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'dosbox-staging', cmd, env).returncode

WIN9X_CD_SUFFIXES = ('.cue', '.iso', '.chd')
WIN9X_CD_CACHE = CACHE / 'win98' / 'dosbox-x'
WIN9X_CONFIG = """[sdl]
fullscreen=true
output=opengl

[dosbox]
machine=svga_s3trio64
memsize=128

[cpu]
core=dynamic
cputype=pentium_mmx
cycles=max

[pci]
voodoo=true

[sblaster]
sbtype=sb16

[dos]
ver=7.1
"""

def _win9x_system_disk() -> Optional[Path]:
    base = hippos_win9x.base_image()
    if base is None:
        return None
    disk = SAVES / 'win98' / 'dosbox-x' / base.name
    if not disk.exists():
        disk.parent.mkdir(parents=True, exist_ok=True)
        _log.info("dosbox-x: copying %s to %s (first use)", base, disk)
        partial = disk.with_suffix(disk.suffix + '.part')
        shutil.copyfile(base, partial)
        partial.replace(disk)
    return disk

def _win9x_game_cd(rom: Path) -> Optional[Path]:
    if rom.suffix.lower() in WIN9X_CD_SUFFIXES:
        return rom
    target = WIN9X_CD_CACHE / rom.stem
    if not target.is_dir():
        shutil.rmtree(WIN9X_CD_CACHE, ignore_errors=True)
        target.mkdir(parents=True)
        _log.info("dosbox-x: unpacking %s", rom.name)
        with zipfile.ZipFile(rom) as archive:
            archive.extractall(target)
    images = sorted(p for p in target.rglob('*') if p.suffix.lower() in WIN9X_CD_SUFFIXES)
    return next((p for p in images if p.suffix.lower() == '.cue'), images[0] if images else None)

def _launch_dosbox_x_win9x(ctx: LaunchContext, bin_path: Path) -> int:
    disk = _win9x_system_disk()
    if disk is None:
        _log.error("dosbox-x: no Windows 9x disk image (%s) in %s", ', '.join(hippos_win9x.IMAGE_PATTERNS), BIOS)
        return 1
    cd = _win9x_game_cd(ctx.rom)
    if cd is None:
        _log.error("dosbox-x: no CD image (%s) in %s", ', '.join(WIN9X_CD_SUFFIXES), ctx.rom)
        return 1
    generated = CACHE / 'win98' / 'dosbox-x.conf'
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(WIN9X_CONFIG + '\n[autoexec]\n'
                         f'imgmount c "{disk}" -ide 1m\n'
                         f'imgmount d "{cd}" -t iso -ide 2m\n'
                         'boot c:\n')
    cmd = [str(bin_path), '-fastbioslogo', '-conf', str(generated)]
    user_conf = CONFIGS / 'dosbox' / 'dosboxx-win98.conf'
    if user_conf.exists():
        cmd += ['-conf', str(user_conf)]
    env = _build_game_env(_load_hippos_conf(), ctx)
    return _run_game_command(ctx, 'dosbox-x', cmd, env).returncode

def launch_dosbox_x(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    rom  = ctx.rom
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('dosbox-x')
    if bin_path is None:
        _log.error("dosbox-x: binary not found")
        return 1
    if ctx.system == 'win98':
        return _launch_dosbox_x_win9x(ctx, bin_path)

    cfg_dir = CONFIGS / 'dosbox'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    custom_cfg = cfg_dir / 'dosboxx-custom.conf'

    base_cfg = rom.parent / 'dosbox.cfg'
    if base_cfg.exists() and not custom_cfg.exists():
        shutil.copy2(base_cfg, custom_cfg)

    if not custom_cfg.exists():
        custom_cfg.write_text('[sdl]\noutput=opengl\n\n[autoexec]\n')

    aut = rom.parent / 'dosbox.aut'
    if aut.exists():
        existing = custom_cfg.read_text()
        if '[autoexec]' in existing:
            existing = existing.rstrip() + '\n' + aut.read_text()
            custom_cfg.write_text(existing)

    cmd = [
        str(bin_path),
        '-fastbioslogo', '-exit',
        '-conf', str(custom_cfg),
        '-c', f'mount c "{rom.parent}"',
        '-c', 'c:',
        '-c', str(rom.name if not rom.is_dir() else 'dosbox.bat'),
    ]

    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'dosbox-x', cmd, env).returncode

_HATARI_MACHINES = {'st', 'ste', 'megaste', 'tt', 'falcon'}
_HATARI_EXTS_FLOPPY = {'.st', '.msa', '.stx', '.dim', '.ipf'}
_HATARI_EXTS_HDD    = {'.hd', '.hdv', '.gem', '.sh3'}
_HATARI_EXTS_ACSI   = {'.img', '.vhd'}

def _hatari_find_tos(machine: str) -> Optional[Path]:
    bios_dir = BIOS
    patterns = ['tos*.img', 'tos*.rom', 'TOS*.img', 'TOS*.ROM', '*.img', '*.rom']
    for pat in patterns:
        for candidate in sorted(bios_dir.glob(pat)):
            return candidate
    return None

def launch_hatari(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    rom  = ctx.rom
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('hatari')
    if bin_path is None:
        _log.error("hatari: binary not found")
        return 1

    machine = _conf_value(conf, 'hatari.machine', 'st')
    if machine not in _HATARI_MACHINES:
        machine = 'st'

    cfg_dir  = CONFIGS / 'hatari'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / 'hatari.cfg'

    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    if cfg_file.exists():
        parser.read(str(cfg_file))

    profiles = _load_es_input_configs()

    for i in range(1, 6):
        section = f'Joystick{i}'
        if parser.has_section(section):
            parser.set(section, 'nJoyId',        '-1')
            parser.set(section, 'nJoystickMode', '0')

    for ctrl in ctx.controllers[:5]:
        profile = _pick_es_profile(profiles, ctrl)
        section = f'Joystick{ctrl.player}'
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, 'nJoyId',        str(ctrl.index))
        parser.set(section, 'nJoystickMode', '1')

        _pad_map = {'y': 'nButton1', 'b': 'nButton2', 'a': 'nButton3'}
        _defaults = {'nButton1': '0', 'nButton2': '1', 'nButton3': '2'}
        if profile is not None:
            for es_name, cfg_key in _pad_map.items():
                binding = profile.inputs.get(es_name)
                parser.set(section, cfg_key,
                            str(binding.code) if binding and binding.type == 'button'
                            else _defaults[cfg_key])
        else:
            for cfg_key, default in _defaults.items():
                parser.set(section, cfg_key, default)

    if not parser.has_section('Log'):
        parser.add_section('Log')
    parser.set('Log', 'bConfirmQuit', 'FALSE')

    with cfg_file.open('w') as f:
        parser.write(f)

    cmd = [str(bin_path), '--fullscreen', '--machine', machine]

    tos = _hatari_find_tos(machine)
    if tos:
        cmd += ['--tos', str(tos)]

    cmd += ['--configfile', str(cfg_file)]

    ext = rom.suffix.lower()
    if ext in _HATARI_EXTS_FLOPPY:
        cmd += ['--disk-a', str(rom), '--drive-b', 'off']
    elif ext in _HATARI_EXTS_HDD:
        cmd += ['--harddrive', str(rom)]
    elif ext in _HATARI_EXTS_ACSI:
        cmd += ['--acsi', str(rom)]
    else:
        cmd.append(str(rom))

    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'hatari', cmd, env).returncode

def launch_scummvm(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    rom  = ctx.rom
    saves_dir   = SAVES / 'scummvm'
    extra_dir   = BIOS / 'scummvm' / 'extra'
    cfg_dir     = CONFIGS / 'scummvm'
    for directory in (saves_dir, extra_dir, cfg_dir, SCREENSHOTS):
        directory.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('scummvm')
    if bin_path is None:
        _log.error("scummvm: binary not found")
        return 1

    ini = cfg_dir / 'scummvm.ini'
    if not ini.exists():
        ini.write_text('[scummvm]\ngui_browser_native=false\n')

    renderer = _conf_value(conf, 'scummvm.renderer', 'opengl')
    scaler   = _conf_value(conf, 'scummvm.scaler', 'normal')
    lang     = _conf_value(conf, f'{ctx.system}.language', '')

    p1 = next((c for c in ctx.controllers if c.player == 1), None)

    cmd = [
        str(bin_path),
        '-f',
        f'--renderer={renderer}',
        f'--scaler={scaler}',
        f'--screenshotpath={SCREENSHOTS}',
        f'--extrapath={extra_dir}',
        f'--savepath={saves_dir}',
        f'--config={ini}',
    ]

    if lang:
        cmd += ['-q', lang]
    if p1 is not None:
        cmd += [f'--joystick={p1.index}']

    if rom.suffix.lower() == '.scummvm':
        game_id = rom.read_text(encoding='utf-8', errors='replace').strip() or rom.stem
        cmd += [f'--path={rom.parent}', game_id]
    elif rom.is_dir():
        cmd += [f'--path={rom}', '--auto-detect']
    else:
        cmd += [f'--path={rom.parent}', '--auto-detect']

    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'scummvm', cmd, env).returncode

def launch_mupen64plus(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    rom  = ctx.rom
    saves_dir   = SAVES / ctx.system
    cfg_dir     = CONFIGS / 'mupen64plus'
    saves_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('mupen64plus')
    if bin_path is None:
        _log.error("mupen64plus: binary not found")
        return 1

    cfg_file = cfg_dir / 'mupen64plus-custom.ini'
    parser = configparser.ConfigParser(strict=False)
    if cfg_file.exists():
        parser.read(str(cfg_file))

    resolution = ctx.resolution or (1920, 1080)
    w, h = resolution
    video_plugin = _conf_value(conf, 'mupen64plus.video', 'gliden64')

    for section, pairs in {
        'Core': [
            ('Version',                '1.01'),
            ('ScreenshotPath',         str(SCREENSHOTS)),
            ('SaveStatePath',          str(saves_dir)),
            ('SaveSRAMPath',           str(saves_dir)),
            ('SharedDataPath',         str(cfg_dir)),
            ('SaveFilenameFormat',     '1000'),
        ],
        'Video-General': [
            ('ScreenWidth',  str(w)),
            ('ScreenHeight', str(h)),
            ('Fullscreen',   'False'),
            ('VerticalSync', 'True'),
        ],
        'Audio-SDL': [
            ('AUDIO_SYNC',              'True'),
            ('PRIMARY_BUFFER_SIZE',    '16384'),
            ('PRIMARY_BUFFER_TARGET',   '2048'),
            ('SECONDARY_BUFFER_SIZE',  '1024'),
        ],
    }.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for k, v in pairs:
            if not parser.has_option(section, k):
                parser.set(section, k, v)

    with cfg_file.open('w') as f:
        parser.write(f)

    lib_dirs = [
        Path('/opt/emulators/mupen64plus/lib'),
        Path('/usr/lib/mupen64plus'),
        Path('/usr/local/lib/mupen64plus'),
    ]
    core_lib = None
    gfx_lib  = None
    for d in lib_dirs:
        if not d.exists():
            continue
        for candidate in d.glob('libmupen64plus.so*'):
            core_lib = candidate
        for name in (f'mupen64plus-video-{video_plugin}.so',
                     f'mupen64plus-video-gliden64.so',
                     f'mupen64plus-video-rice.so'):
            candidate = d / name
            if candidate.exists():
                gfx_lib = candidate
                break
        if core_lib:
            break

    cmd = [str(bin_path)]
    if core_lib:
        cmd += ['--corelib', str(core_lib)]
    if gfx_lib:
        cmd += ['--gfx', str(gfx_lib)]
    cmd += [
        '--configdir', str(cfg_dir),
        '--datadir',   str(cfg_dir),
        str(rom),
    ]

    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'mupen64plus', cmd, env).returncode

_FSUAE_MODELS = {
    'A500':  'A500',  'A500+': 'A500+', 'A600': 'A600',
    'A1000': 'A1000', 'A3000': 'A3000', 'A1200': 'A1200',
    'A4000': 'A4000', 'CD32':  'CD32',  'CDTV': 'CDTV',
}

def _fsuae_floppy_list(rom: Path) -> list[Path]:
    if not rom.is_dir() and zipfile.is_zipfile(rom):
        tmp = Path('/tmp/fsuae') / rom.stem
        tmp.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(rom) as z:
            z.extractall(tmp)
        rom = tmp

    if rom.is_dir():
        return sorted(p for p in rom.iterdir()
                      if p.suffix.lower() in ('.adf', '.adz', '.dms', '.fdi', '.ipf'))

    stem = rom.stem
    base = stem.rstrip('0123456789')
    siblings = sorted(p for p in rom.parent.iterdir()
                      if p.stem.startswith(base) and p.suffix == rom.suffix)
    return siblings if len(siblings) > 1 else [rom]

def launch_fsuae(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    rom  = ctx.rom
    cfg_dir   = CONFIGS / 'fs-uae'
    saves_dir = SAVES / ctx.system
    cfg_dir.mkdir(parents=True, exist_ok=True)
    saves_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('fsuae')
    if bin_path is None:
        _log.error("fs-uae: binary not found")
        return 1

    model = _conf_value(conf, f'{ctx.system}.fsuae_model', '')
    if not model:
        model = _conf_value(conf, 'fsuae.model', '')
    model = _FSUAE_MODELS.get(model, 'A500')

    cmd = [
        str(bin_path),
        '--fullscreen',
        f'--amiga-model={model}',
        f'--base_dir={cfg_dir}',
        f'--kickstarts_dir={BIOS}',
        f'--save_states_dir={saves_dir}',
        '--zoom=auto',
    ]

    ext = rom.suffix.lower()
    if ext in ('.cue', '.iso', '.chd') or model in ('CD32', 'CDTV'):
        cmd.append(f'--cdrom_image_0={rom}')
    else:
        floppies = _fsuae_floppy_list(rom)
        for i, floppy in enumerate(floppies[:4]):
            cmd.append(f'--floppy_image_{i}={floppy}')
            cmd.append(f'--floppy_drive_{i}={floppy}')

    for ctrl in ctx.controllers[:4]:
        port_name = ctrl.name if ctrl.name else 'auto'
        cmd.append(f'--joystick_port_{ctrl.player - 1}={port_name}')

    env = _build_game_env(conf, ctx)
    return _run_game_command(ctx, 'fsuae', cmd, env).returncode

_BASILISK2_ROM_DIR = BIOS / 'macintosh'

def launch_basilisk2(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('basilisk2')
    if bin_path is None:
        _log.error("basilisk2: binary not found")
        return 1
    mac_rom = next((path for path in sorted(_BASILISK2_ROM_DIR.glob('*'))
                    if path.suffix.lower() == '.rom'), None)
    if mac_rom is None:
        _log.error("basilisk2: no Macintosh ROM (*.rom) in %s", _BASILISK2_ROM_DIR)
        return 1
    prefs = CONFIGS / 'basilisk2' / 'prefs'
    prefs.parent.mkdir(parents=True, exist_ok=True)
    managed = {
        'rom': str(mac_rom),
        'disk': str(ctx.rom),
        'nogui': 'true',
        'screen': 'dga/0/0',
    }
    kept = [line for line in (prefs.read_text(encoding='utf-8').splitlines() if prefs.exists() else [])
            if line.split(' ', 1)[0] not in managed]
    prefs.write_text('\n'.join([*kept, *(f'{key} {value}' for key, value in managed.items())]) + '\n',
                     encoding='utf-8')
    cmd = [str(bin_path), '--config', str(prefs)]
    env = _build_game_env(_load_hippos_conf(), ctx)
    return _run_game_command(ctx, 'basilisk2', cmd, env).returncode

_OPENMSX_MACHINES = {
    'msx1':       'Boosted_MSX2_EN',
    'msx2':       'Boosted_MSX2_EN',
    'msx2+':      'Boosted_MSX2+_JP',
    'msxturbor':  'Boosted_MSXturboR_with_IDE',
    'colecovision': 'ColecoVision_SGM',
    'spectravideo': 'Spectravideo_SVI-328',
}
_OPENMSX_LASERDISC_MACHINE = 'Pioneer_PX-7'

_OPENMSX_MEDIA_EXTS = {
    '.rom': '-cart', '.ri': '-cart', '.mx1': '-cart', '.mx2': '-cart',
    '.col': '-cart',
    '.dsk': '-diska', '.dmk': '-diska',
    '.cas': '-cassetteplayer',
    '.ogv': '-laserdisc',
}

def _openmsx_write_settings(cfg_dir: Path, system_share: Path, controllers: list[ControllerInfo]) -> Path:
    share_dir = cfg_dir / 'share'
    share_dir.mkdir(parents=True, exist_ok=True)

    settings_file = share_dir / 'settings.xml'
    root = ET.Element('settings')
    values_el = ET.SubElement(root, 'settings')

    def _setting(name: str, value: str) -> None:
        el = ET.SubElement(values_el, 'setting', id=name)
        el.text = value

    _setting('fullspeedwhenloading', 'true')
    _setting('save_settings_on_exit', 'false')
    _setting('__filepool', ' '.join((
        f'{{-path {BIOS}/Machines -types system_rom}}',
        f'{{-path {BIOS}/openmsx -types system_rom}}',
        f'{{-path {system_share}/systemroms -types system_rom}}',
        f'{{-path {share_dir}/software -types {{rom disk tape}}}}',
    )))

    bindings_el = ET.SubElement(root, 'bindings')
    for key, cmd in (
        ('keyb F6', 'cycle videosource'),
        ('keyb F5', f'screenshot -prefix {SCREENSHOTS}/'),
    ):
        bind_el = ET.SubElement(bindings_el, 'bind')
        bind_el.set('key', key)
        bind_el.text = cmd

    ET.indent(root, space='  ')
    settings_file.write_text(
        '<?xml version="1.0"?>\n'
        "<!DOCTYPE settings SYSTEM 'settings.dtd'>\n"
        + ET.tostring(root, encoding='unicode') + '\n',
        encoding='utf-8',
    )

    script_file = share_dir / 'script.tcl'
    profiles = _load_es_input_configs()
    lines = ['# -= Controller config =-']
    joy_ports = ['joyporta', 'joyportb']
    for i, ctrl in enumerate(controllers[:2]):
        joy_num = i + 1
        port    = joy_ports[i]
        lines.append(f'plug {port} joystick{joy_num}')
        lines.append(f'dict set joystick{joy_num}_config LEFT  {{-axis0 L_hat0}}')
        lines.append(f'dict set joystick{joy_num}_config RIGHT {{+axis0 R_hat0}}')
        lines.append(f'dict set joystick{joy_num}_config UP    {{-axis1 U_hat0}}')
        lines.append(f'dict set joystick{joy_num}_config DOWN  {{+axis1 D_hat0}}')

        profile = _pick_es_profile(profiles, ctrl)
        if profile is not None:
            for es_name, tcl_cmd in (
                ('y',        f'"keymatrixdown 6 0x40"'),
                ('x',        f'"keymatrixdown 6 0x80"'),
                ('pagedown', None),
                ('select',   f'"toggle pause"'),
                ('start',    f'"main_menu_toggle"'),
                ('l3',       f'"toggle_osd_keyboard"'),
                ('r3',       f'"toggle console"'),
            ):
                binding = profile.inputs.get(es_name)
                if binding is None or binding.type != 'button':
                    continue
                if es_name == 'pagedown':
                    lines.append(f'bind "joy{joy_num} button{binding.code} up"   "set fastforward off"')
                    lines.append(f'bind "joy{joy_num} button{binding.code} down" "set fastforward on"')
                else:
                    lines.append(f'bind "joy{joy_num} button{binding.code} down" {tcl_cmd}')

    script_file.write_text('\n'.join(lines) + '\n')
    return share_dir

def launch_openmsx(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    rom  = ctx.rom
    cfg_dir   = CONFIGS / 'openmsx'
    saves_dir = SAVES / ctx.system
    cfg_dir.mkdir(parents=True, exist_ok=True)
    saves_dir.mkdir(parents=True, exist_ok=True)

    bin_path = _find_emulator_bin('openmsx')
    if bin_path is None:
        _log.error("openmsx: binary not found")
        return 1

    system_share = bin_path.parent.parent / 'share'
    share_dir = _openmsx_write_settings(cfg_dir, system_share, ctx.controllers)

    machine = _OPENMSX_MACHINES.get(ctx.system, 'Boosted_MSX2_EN')

    if rom.suffix.lower() == '.zip' and zipfile.is_zipfile(rom):
        tmp = Path('/tmp/openmsx') / rom.stem
        tmp.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(rom) as z:
            z.extractall(tmp)
        candidates = list(tmp.iterdir())
        if candidates:
            rom = candidates[0]

    media_flag = _OPENMSX_MEDIA_EXTS.get(rom.suffix.lower(), '-cart')
    if media_flag == '-laserdisc':
        machine = _OPENMSX_LASERDISC_MACHINE

    cmd = [
        str(bin_path),
        '-machine', machine,
        media_flag, str(rom),
        '-script',  str(share_dir / 'script.tcl'),
    ]

    env = _build_game_env(conf, ctx)
    env['OPENMSX_HOME'] = str(cfg_dir)
    env['OPENMSX_SYSTEM_DATA'] = str(system_share)
    return _run_game_command(ctx, 'openmsx', cmd, env).returncode
