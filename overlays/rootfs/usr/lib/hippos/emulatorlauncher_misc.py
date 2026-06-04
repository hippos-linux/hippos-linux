from __future__ import annotations

import configparser
import json
import os
from pathlib import Path

from emulatorlauncher_impl import (
    BIOS,
    CACHE,
    CONFIGS,
    CLK_QUICKLOAD_SYSTEMS,
    CLK_RGB_SYSTEMS,
    CLK_SVIDEO_SYSTEMS,
    LaunchContext,
    SAVES,
    TSUGARU_CD_SYSTEMS,
    USERDATA,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _find_emulator_bin,
    _find_emulator_bin_in_package,
    _load_es_input_configs,
    _load_hippos_conf,
    _log,
    _pick_es_profile,
    _run_game_command,
    generate_sdl_game_controller_config,
)


# Vice joystick action mapping
# Format: "# inputindex action / port_pin"  (# = pad.index, ? = button.id)
_VICE_JOY_MAP: dict[str, str] = {
    'up':       '# 2 0 1 / 1',
    'down':     '# 2 1 1 / 2',
    'left':     '# 2 2 1 / 4',
    'right':    '# 2 3 1 / 8',
    'start':    '# 1 ? 0',
    'select':   '# 1 ? 4',
    'hotkey':   '# 1 ? 5 Quit emulator',
    'a':        '# 1 ? 1 / 32',
    'b':        '# 1 ? 1 / 16',
    'x':        '# 1 ? 0',
    'y':        '# 1 ? 1 / 64',
    'pageup':   '# 1 ? 0',
    'pagedown': '# 1 ? 0',
}


def _write_vice_joymap(ctx: LaunchContext) -> None:
    """Write VICE SDL joystick mapping file."""
    vice_cfg_dir = CONFIGS / 'vice'
    vice_cfg_dir.mkdir(parents=True, exist_ok=True)
    vjm_path = vice_cfg_dir / 'sdl-joymap.vjm'

    profiles = _load_es_input_configs()
    joy_port = '0' if (ctx.core or '').startswith('xvic') else '1'

    lines = ['# HippOS configured controllers', '', '!CLEAR']
    for ctrl in ctx.controllers:
        profile = _pick_es_profile(profiles, ctrl)
        if profile is None:
            continue
        lines.append('')
        lines.append(f'# {ctrl.name}')
        for es_name, template in _VICE_JOY_MAP.items():
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            line = template.replace('#', str(ctrl.index)).replace('?', str(binding.code)).replace('/', joy_port)
            lines.append(line)
        lines.append('')

    vjm_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    _log.info("Wrote Vice joymap: %s", vjm_path)


def launch_vice(ctx: LaunchContext) -> int:
    binary = ctx.core or 'x64'
    bin_path = _find_emulator_bin_in_package('vice', binary)
    if bin_path is None:
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_vice_joymap(ctx)
    cmd = [str(bin_path), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'vice', cmd, env)
    return result.returncode


def launch_simcoupe(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin_in_package('samcoupe', 'samcoupe', 'simcoupe')
    if bin_path is None:
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    cmd = [str(bin_path), 'autoboot', '-disk1', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'samcoupe', cmd, env)
    return result.returncode


def launch_sh(ctx: LaunchContext) -> int:
    rom = ctx.rom
    # squashfs mounts arrive as a directory; look for run.sh inside
    script = (rom / 'run.sh') if rom.is_dir() and (rom / 'run.sh').exists() else rom
    if not script.exists():
        return 1
    mode = script.stat().st_mode
    if not (mode & 0o111):
        try:
            script.chmod(mode | 0o111)
        except PermissionError:
            pass  # already executable or on a filesystem that doesn't support chmod
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    result = _run_game_command(ctx, 'shell', ['/bin/bash', str(script)], env,
                               cwd=script.parent)
    return result.returncode


def launch_flatpak(ctx: LaunchContext) -> int:
    try:
        app_id = ctx.rom.read_text(encoding='utf-8').strip()
    except OSError as exc:
        _log.error("Could not read Flatpak app ID from %s: %s", ctx.rom, exc)
        return 1
    if not app_id:
        _log.error("Empty Flatpak app ID in %s", ctx.rom)
        return 1
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI_XBOX'] = '0'
    cmd = ['/usr/bin/flatpak', 'run', app_id]
    _log.info("Launching Flatpak: %s", app_id)
    result = _run_game_command(ctx, 'flatpak', cmd, env)
    return result.returncode


def launch_pygame(ctx: LaunchContext) -> int:
    pygame_dir = Path('/opt/emulators/python-pygame2')
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    if pygame_dir.exists():
        env['PYTHONPATH'] = str(pygame_dir) + ':' + env.get('PYTHONPATH', '')
        libs = str(pygame_dir / 'pygame.libs')
        env['LD_LIBRARY_PATH'] = libs + ':' + env.get('LD_LIBRARY_PATH', '')
    result = _run_game_command(ctx, 'pygame', ['python3', str(ctx.rom)], env,
                               cwd=ctx.rom.parent)
    return result.returncode


def launch_ruffle(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('ruffle')
    if bin_path is None:
        return 1
    conf = _load_hippos_conf()
    cmd = [str(bin_path), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'ruffle', cmd, env)
    return result.returncode


def launch_lightspark(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('lightspark')
    if bin_path is None:
        return 1
    conf = _load_hippos_conf()
    cmd = [str(bin_path), '-fs', '-s', 'local-with-networking', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'lightspark', cmd, env)
    return result.returncode


def launch_pyxel(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('pyxel')
    if bin_path is None:
        return 1
    conf = _load_hippos_conf()
    cmd = [str(bin_path), 'play' if ctx.rom.suffix == '.pyxapp' else 'run', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'pyxel', cmd, env)
    return result.returncode


def launch_clk(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('clksignal', 'clk')
    if bin_path is None:
        return 1
    if ctx.rom.is_dir():
        return 1
    conf = _load_hippos_conf()
    cmd: list[str] = [str(bin_path), str(ctx.rom), '--rompath=/userdata/bios/']
    if ctx.system in CLK_SVIDEO_SYSTEMS:
        cmd.append('--output=SVideo')
    if ctx.system in CLK_RGB_SYSTEMS:
        cmd.append('--output=RGB')
    if ctx.system in CLK_QUICKLOAD_SYSTEMS:
        cmd.append('--accelerate-media-loading')
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'clk', cmd, env)
    return result.returncode


def launch_tsugaru(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('Tsugaru_CUI', 'tsugaru')
    if bin_path is None:
        return 1
    conf = _load_hippos_conf()
    cmd: list[str] = [str(bin_path), str(BIOS / 'fmtowns'), '-FULLSCREEN', '-NOHIGHRESPCM', '-NOWAITBOOT', '-AUTOSCALE', '-MAINTAINASPECT', '-HIGHRES', '-GAMEPORT0', 'KEY', '-KEYBOARD', 'DIRECT', '-PAUSEKEY', 'F10']
    if (cdrom_speed := _conf_value(conf, 'cdrom_speed', 'auto')) != 'auto':
        cmd += ['-CDSPEED', cdrom_speed]
    if _conf_bool(conf, '386dx', False):
        cmd.append('-PRETEND386DX')
    if ctx.rom.suffix.lower() in TSUGARU_CD_SYSTEMS:
        cmd += ['-CD', str(ctx.rom)]
    else:
        cmd += ['-FD0', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'tsugaru', cmd, env)
    return result.returncode


def launch_x16emu(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('x16emu')
    if bin_path is None:
        return 1
    conf = _load_hippos_conf()
    romdir = ctx.rom.parent
    cmd: list[str] = [
        str(bin_path),
        '-rom', '/userdata/bios/commanderx16/rom.bin',
        '-fsroot', str(romdir),
        '-ram', '2048',
        '-rtc',
    ]
    if ctx.rom.suffix == '.img':
        cmd += ['-sdcard', str(ctx.rom)]
    elif ctx.rom.suffix == '.bas':
        cmd += ['-bas', str(ctx.rom)]
    else:
        cmd += ['-prg', str(ctx.rom), '-run']
    autorun_cmd = romdir / 'autorun.cmd'
    if autorun_cmd.exists():
        cmd += ['-bas', str(autorun_cmd)]
    cmd += ['-scale', _conf_value(conf, 'x16emu_scale', '2')]
    if (quality := _conf_value(conf, 'x16emu_quality', '')):
        cmd += ['-quality', quality]
    if _conf_value(conf, 'x16emu_ratio', '') == '16:9':
        cmd.append('-widescreen')
    for nplayer, _ in enumerate(ctx.controllers[:4], start=1):
        cmd.append(f'-joy{nplayer}')
    env = _build_game_env(conf, ctx)
    env['XDG_DATA_HOME'] = str(CACHE)
    result = _run_game_command(ctx, 'x16emu', cmd, env)
    return result.returncode


def launch_ioquake3(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('ioquake3')
    if bin_path is None:
        _log.error("ioquake3 not installed")
        return 1
    conf = _load_hippos_conf()
    cmd: list[str] = [str(bin_path)]
    # .quake3 rom file contains command-line args (e.g. +set fs_game baseq3)
    try:
        args = ctx.rom.read_text(encoding='utf-8').strip().split()
        cmd.extend(args)
    except OSError:
        pass
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    result = _run_game_command(ctx, 'ioquake3', cmd, env, cwd=ctx.rom.parent)
    return result.returncode


def launch_lexaloffle(ctx: LaunchContext) -> int:
    system = ctx.system  # 'pico8' or 'voxatron'
    if system == 'pico8':
        bin_path = BIOS / 'pico-8' / 'pico8'
        controllers_file = USERDATA / '.lexaloffle' / 'pico-8' / 'sdl_controllers.txt'
        roms_dir = USERDATA / 'roms' / 'pico8'
        ld_lib = BIOS / 'pico-8'
    else:
        bin_path = BIOS / 'voxatron' / 'vox'
        controllers_file = USERDATA / '.lexaloffle' / 'Voxatron' / 'sdl_controllers.txt'
        roms_dir = USERDATA / 'roms' / 'voxatron'
        ld_lib = BIOS / 'voxatron'

    if not bin_path.exists():
        _log.error("Lexaloffle binary not found at %s (user must provide)", bin_path)
        return 1

    controllers_file.parent.mkdir(parents=True, exist_ok=True)
    controllers_file.write_text(generate_sdl_game_controller_config(ctx.controllers))

    conf = _load_hippos_conf()
    cmd: list[str] = [str(bin_path), '-windowed', '0']

    rombase = ctx.rom.stem
    if ctx.rom.suffix.lower() == '.m3u':
        lines = ctx.rom.read_text(encoding='utf-8').splitlines()
        if lines:
            target = ctx.rom.parent / lines[0].strip()
            cmd += ['-root_path', str(target.parent), '-run', str(target)]
        else:
            cmd += ['-root_path', str(roms_dir)]
    elif rombase.lower() in ('splore', 'console'):
        cmd += ['-root_path', str(roms_dir), '-splore']
    else:
        cmd += ['-root_path', str(roms_dir), '-run', str(ctx.rom)]

    env = _build_game_env(conf, ctx)
    existing_ld = env.get('LD_LIBRARY_PATH', '')
    env['LD_LIBRARY_PATH'] = f"{ld_lib}:{existing_ld}" if existing_ld else str(ld_lib)
    result = _run_game_command(ctx, 'lexaloffle', cmd, env)
    return result.returncode


def launch_uqm(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('urquan', 'uqm')
    if bin_path is None:
        _log.error("uqm (urquan) not installed")
        return 1
    saves_dir = SAVES / 'uqm'
    roms_dir = USERDATA / 'roms' / 'uqm'
    for d in (saves_dir / 'teams', saves_dir / 'save'):
        d.mkdir(parents=True, exist_ok=True)
    (roms_dir / 'version').touch(exist_ok=True)
    conf = _load_hippos_conf()
    cmd = [str(bin_path), f'--contentdir={roms_dir}', f'--configdir={saves_dir}']
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    result = _run_game_command(ctx, 'uqm', cmd, env)
    return result.returncode


def launch_redream(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('redream')
    if bin_path is None:
        _log.error("redream not installed")
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf      = _load_hippos_conf()
    profiles  = _load_es_input_configs()
    cfg_dir   = bin_path.parent
    cfg_file  = cfg_dir / 'redream.cfg'

    w, h = ctx.resolution if ctx.resolution else (1920, 1080)

    _btn_map = {'a': 'b', 'b': 'a', 'x': 'y', 'y': 'x', 'start': 'start', 'select': 'menu', 'pageup': 'turbo'}
    _hat_map = {'up': 0, 'down': 1, 'left': 2, 'right': 3}

    lines: list[str] = [
        f'gamedir={SAVES / ctx.system}',
        'mode=exclusive fullscreen',
        'fullmode=exclusive fullscreen',
    ]
    seen_guids: set[str] = set()
    for ctrl in ctx.controllers[:4]:
        lines.append(f'port{ctrl.index}=dev:{4 + ctrl.index},desc:{ctrl.guid},type:controller')
        if ctrl.guid in seen_guids:
            continue
        seen_guids.add(ctrl.guid)
        profile = _pick_es_profile(profiles, ctrl)
        profile_str = f'profile{ctrl.index}=name:{ctrl.guid},type:controller,deadzone:12,crosshair:1,'
        if profile:
            for inp in profile.inputs.values():
                if inp.type == 'button' and inp.name in _btn_map:
                    profile_str += f'{_btn_map[inp.name]}:joy{inp.code},'
                elif inp.type == 'button' and inp.name == 'l2':
                    profile_str += f'ltrig:joy{inp.code},'
                elif inp.type == 'button' and inp.name == 'r2':
                    profile_str += f'rtrig:joy{inp.code},'
                elif inp.type == 'button' and inp.name in _hat_map:
                    profile_str += f'dpad_{inp.name}:joy{inp.code},'
                elif inp.type == 'hat' and inp.name in _hat_map:
                    profile_str += f'dpad_{inp.name}:hat{_hat_map[inp.name]},'
                elif inp.type == 'axis' and inp.name == 'l2':
                    profile_str += f'ltrig:+axis{inp.code},'
                elif inp.type == 'axis' and inp.name == 'r2':
                    profile_str += f'rtrig:+axis{inp.code},'
                elif inp.type == 'axis' and inp.name == 'joystick1left':
                    profile_str += f'ljoy_left:-axis{inp.code},ljoy_right:+axis{inp.code},'
                elif inp.type == 'axis' and inp.name == 'joystick1up':
                    profile_str += f'ljoy_up:-axis{inp.code},ljoy_down:+axis{inp.code},'
        profile_str += 'exit:f10'
        lines.append(profile_str)

    lines += [
        f'width={w}', f'height={h}', f'fullwidth={w}', f'fullheight={h}',
        f'res={_conf_value(conf, "redreamResolution", "2")}',
        f'aspect={_conf_value(conf, "redreamRatio", "4:3")}',
        f'frameskip={_conf_value(conf, "redreamFrameSkip", "0")}',
        f'vsync={_conf_value(conf, "redreamVsync", "0")}',
        f'renderer={_conf_value(conf, "redreamRender", "hle_perstrip")}',
        f'region={_conf_value(conf, "redreamRegion", "usa")}',
        f'language={_conf_value(conf, "redreamLanguage", "english")}',
        f'broadcast={_conf_value(conf, "redreamBroadcast", "ntsc")}',
        f'cable={_conf_value(conf, "redreamCable", "vga")}',
    ]
    cfg_file.write_text('\n'.join(lines) + '\n')

    cmd = [str(bin_path), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    env['SDL_AUDIODRIVER']     = 'alsa'
    result = _run_game_command(ctx, 'redream', cmd, env)
    return result.returncode


def launch_corsixth(ctx: LaunchContext) -> int:
    import locale
    bin_path = _find_emulator_bin('corsixth', 'corsix-th', 'CorsixTH')
    if bin_path is None:
        _log.error("corsixth not installed")
        return 1
    cfg_dir      = CONFIGS / 'corsixth'
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file     = cfg_dir / 'config.txt'
    hospital_dir = USERDATA / 'roms' / 'corsixth'
    saves_dir    = SAVES / 'corsixth'
    screenshots  = USERDATA / 'screenshots'
    saves_dir.mkdir(parents=True, exist_ok=True)

    w, h = ctx.resolution if ctx.resolution else (1920, 1080)
    conf = _load_hippos_conf()

    # Language mapping from system locale
    _lang_map = {
        'en_US': 'en', 'en_GB': 'en', 'fr_FR': 'fr', 'oc_FR': 'fr',
        'de_DE': 'de', 'es_ES': 'es', 'es_MX': 'es', 'it_IT': 'it',
        'nl_NL': 'nl', 'ru_RU': 'ru', 'sv_SE': 'sv', 'cs_CZ': 'cs',
        'fi_FI': 'fi', 'pl_PL': 'pl', 'hu_HU': 'hu', 'pt_PT': 'pt',
        'pt_BR': 'br', 'zh_CN': 'zhs', 'zh_TW': 'zht', 'ko_KR': 'ko',
        'nb_NO': 'nb', 'nn_NO': 'nb',
    }
    try:
        sys_lang = locale.getdefaultlocale()[0] or 'en_US'
    except Exception:
        sys_lang = 'en_US'
    cth_lang = _lang_map.get(sys_lang[:5], 'en')

    font_path = Path('/usr/share/fonts/dejavu/DejaVuSans.ttf')

    with cfg_file.open('w') as f:
        f.write('check_for_updates = false\n')
        f.write(f'theme_hospital_install = [[{hospital_dir}]]\n')
        if font_path.exists():
            f.write(f'unicode_font = [[{font_path}]]\n')
        f.write(f'savegames = [[{saves_dir}]]\n')
        f.write(f'screenshots = [[{screenshots}]]\n')
        f.write('fullscreen = true\n')
        f.write(f'width = {w}\n')
        f.write(f'height = {h}\n')
        f.write(f'use_new_graphics = {_conf_value(conf, "cth_new_graphics", "true")}\n')
        f.write(f'free_build_mode = {_conf_value(conf, "cth_free_build_mode", "false")}\n')
        f.write(f'play_intro = {_conf_value(conf, "cth_play_intro", "true")}\n')
        f.write(f'language = [[{cth_lang}]]\n')
        mp3_dir = hospital_dir / 'MP3'
        if mp3_dir.exists():
            f.write(f'audio_music = [[{mp3_dir}]]\n')
        else:
            f.write('audio_music = nil\n')

    cmd = [str(bin_path), f'--config-file={cfg_file}']
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'corsixth', cmd, env)
    return result.returncode


_GZDOOM_JOY_BINDINGS: dict[str, str] = {
    'b':        '+use',
    'x':        '+jump',
    'pageup':   'weapnext',
    'pagedown': 'weapprev',
    'l3':       'crouch',
    'start':    'menu_main',
    'select':   'pause',
}
_GZDOOM_JOY_AUTOMAP_BINDINGS: dict[str, str] = {
    'a':        'am_clearmarks',
    'b':        'am_setmark',
    'y':        'am_togglefollow',
    'pageup':   'am_zoomin',
    'pagedown': 'am_zoomout',
}


def _gzdoom_ini_set(sections: dict, section: str, key: str, value: str) -> None:
    sections.setdefault(section, {})[key] = value


def _gzdoom_ini_set_if_missing(sections: dict, section: str, key: str, value: str) -> None:
    sections.setdefault(section, {}).setdefault(key, value)


def _gzdoom_read_ini(path: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current: str = ''
    if not path.exists():
        return sections
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            current = s
            sections.setdefault(current, {})
        elif current and '=' in s:
            k, _, v = s.partition('=')
            sections[current][k.strip()] = v.strip()
    return sections


def _gzdoom_write_ini(path: Path, sections: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for sec, kv in sections.items():
            f.write(f'{sec}\n')
            for k, v in kv.items():
                f.write(f'{k}={v}\n')
            f.write('\n')


def launch_gzdoom(ctx: LaunchContext) -> int:
    import shlex as _shlex
    bin_path = _find_emulator_bin('gzdoom')
    if bin_path is None:
        _log.error("gzdoom not installed")
        return 1
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf    = _load_hippos_conf()
    profiles = _load_es_input_configs()
    cfg_dir = CONFIGS / 'gzdoom'
    cfg_dir.mkdir(parents=True, exist_ok=True)

    ini_path    = cfg_dir / 'gzdoom.ini'
    script_path = cfg_dir / 'gzdoom.cfg'
    logs_dir    = USERDATA / 'system' / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)

    # GPU API selection
    gz_api = _conf_value(conf, 'gz_api', '0')
    if gz_api == '3':
        api_cfg = 'gl_es 1\nvid_preferbackend 3\ngles_use_mapped_buffer true\n'
    else:
        api_cfg = f'vid_preferbackend {gz_api}\n'

    # Script file
    show_fps = _conf_bool(conf, 'show_fps', False)
    script_path.write_text(
        f'logfile "{logs_dir / "gzdoom.log"}"\n'
        f'vid_fps {"true" if show_fps else "false"}\n'
        + api_cfg +
        'echo HIPPOS\n',
        encoding='utf-8',
    )

    # Update INI file with joystick bindings
    sections = _gzdoom_read_ini(ini_path)

    _gzdoom_ini_set(sections, '[GlobalSettings]', 'vid_vsync', _conf_value(conf, 'gz_vsync', 'false'))
    _gzdoom_ini_set(sections, '[GlobalSettings]', 'use_joystick', 'true')

    # ROM search paths
    rom_parent = str(ctx.rom.parent)
    for sec in ('[IWADSearch.Directories]', '[FileSearch.Directories]'):
        existing_vals = set(sections.get(sec, {}).values())
        if f'Path={rom_parent}' not in existing_vals:
            idx = len(sections.get(sec, {}))
            _gzdoom_ini_set_if_missing(sections, sec, f'Path_{idx}', rom_parent)

    # Sound font paths
    for p in ['/usr/share/gzdoom/soundfonts', '/usr/share/gzdoom/fm_banks',
              str(cfg_dir / 'soundfonts'), str(cfg_dir / 'fm_banks')]:
        _gzdoom_ini_set_if_missing(sections, '[SoundfontSearch.Directories]', f'Path_{p}', p)

    # Clear old Joy bindings and rewrite from ES profile
    for bind_sec in ('[Doom.Bindings]', '[Doom.AutomapBindings]'):
        sections.setdefault(bind_sec, {})
        sections[bind_sec] = {k: v for k, v in sections[bind_sec].items()
                               if not k.startswith('Joy')}

    if ctx.controllers:
        p1 = ctx.controllers[0]
        profile = _pick_es_profile(profiles, p1)
        # Enable P1 joystick, disable rest
        for i in range(len(ctx.controllers)):
            _gzdoom_ini_set(sections, f'[Joy:JS:{i}]', 'Enabled', '1' if i == 0 else '0')

        if profile:
            for inp in profile.inputs.values():
                if inp.type != 'button':
                    continue
                joynum = inp.code + 1
                if inp.name in _GZDOOM_JOY_BINDINGS:
                    _gzdoom_ini_set(sections, '[Doom.Bindings]',
                                    f'Joy{joynum}', _GZDOOM_JOY_BINDINGS[inp.name])
                if inp.name in _GZDOOM_JOY_AUTOMAP_BINDINGS:
                    _gzdoom_ini_set(sections, '[Doom.AutomapBindings]',
                                    f'Joy{joynum}', _GZDOOM_JOY_AUTOMAP_BINDINGS[inp.name])

    _gzdoom_write_ini(ini_path, sections)

    w, h = ctx.resolution if ctx.resolution else (1920, 1080)

    if ctx.rom.suffix == '.gzdoom':
        wad_args = _shlex.split(ctx.rom.read_text(encoding='utf-8'))
        cmd = [str(bin_path)] + wad_args
    else:
        cmd = [str(bin_path), '-iwad', ctx.rom.name]

    cmd += ['-exec', str(script_path), '-width', str(w), '-height', str(h)]

    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    result = _run_game_command(ctx, 'gzdoom', cmd, env, cwd=ctx.rom.parent)
    return result.returncode


_RYUJINX_CTRL_TEMPLATE: dict = {
    'left_joycon_stick':  {'joystick': 'Left', 'invert_stick_x': False, 'invert_stick_y': False, 'rotate90_cw': False, 'stick_button': 'LeftStick'},
    'right_joycon_stick': {'joystick': 'Right', 'invert_stick_x': False, 'invert_stick_y': False, 'rotate90_cw': False, 'stick_button': 'RightStick'},
    'deadzone_left': 0, 'deadzone_right': 0, 'range_left': 1, 'range_right': 1, 'trigger_threshold': 0,
    'motion': {'motion_backend': 'GamepadDriver', 'sensitivity': 100, 'gyro_deadzone': 1, 'enable_motion': True},
    'rumble': {'strong_rumble': 8.0, 'weak_rumble': 2.0, 'enable_rumble': True},
    'left_joycon': {
        'button_minus': 'Minus', 'button_l': 'LeftShoulder', 'button_zl': 'LeftTrigger',
        'button_sl': 'Unbound', 'button_sr': 'Unbound',
        'dpad_up': 'DpadUp', 'dpad_down': 'DpadDown', 'dpad_left': 'DpadLeft', 'dpad_right': 'DpadRight',
    },
    'right_joycon': {
        'button_plus': 'Plus', 'button_r': 'RightShoulder', 'button_zr': 'RightTrigger',
        'button_sl': 'Unbound', 'button_sr': 'Unbound',
        'button_x': 'Y', 'button_b': 'A', 'button_y': 'X', 'button_a': 'B',
    },
    'version': 1,
    'backend': 'GamepadSDL2',
}


def _ryujinx_ctrl_uuid(ctrl) -> str:
    """Generate a Ryujinx-compatible device UUID from SDL GUID."""
    guid = (ctrl.guid or '').lower().replace('-', '')
    if len(guid) == 32:
        bustype    = guid[0:8]
        vendor     = guid[8:12]
        product    = guid[16:20]
        version    = guid[24:28]
        prod_rev   = product[2:4] + product[0:2]
        ver_rev    = version[2:4] + version[0:2]
        return f'{ctrl.index}-{bustype}-{vendor}-0000-{prod_rev}-0000{ver_rev}0000'
    return f'{ctrl.index}-00000003-0000-0000-0000-000000000000'


def launch_ryujinx(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('Ryujinx.sh', 'Ryujinx', 'ryujinx')
    if bin_path is None:
        _log.error("ryujinx not installed")
        return 1
    cfg_path = USERDATA / 'system' / 'configs' / 'Ryujinx' / 'Config.json'
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            pass
    cfg['start_fullscreen'] = True
    cfg['docked_mode']      = True
    cfg['input_config']     = []

    for nplayer, ctrl in enumerate(ctx.controllers[:8], start=1):
        ctrl_cfg = dict(_RYUJINX_CTRL_TEMPLATE)
        ctrl_cfg['id']              = _ryujinx_ctrl_uuid(ctrl)
        ctrl_cfg['controller_type'] = 'ProController'
        ctrl_cfg['player_index']    = f'Player{nplayer}'
        cfg['input_config'].append(ctrl_cfg)

    cfg_path.write_text(json.dumps(cfg, indent=2))
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    cmd = [str(bin_path), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'ryujinx', cmd, env)
    return result.returncode
