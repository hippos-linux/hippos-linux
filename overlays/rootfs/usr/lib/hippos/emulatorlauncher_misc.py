from __future__ import annotations

import shlex
import zipfile
from dataclasses import replace
from pathlib import Path
from shutil import which

from emulatorlauncher_shared import (
    _game_bool,
    _game_value,
    LaunchContext,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _find_emulator_bin,
    _load_es_input_configs,
    _load_hippos_conf,
    _log,
    _pick_es_profile,
    _run_game_command,
    generate_sdl_game_controller_config,
    _require_emulator_bin,
    _require_emulator_bin_in_package,
)

from HipposPaths import BIOS, CONFIGS, SAVES, USERDATA
from hippos_launcher_sync import CLIENT_ENTRY
from hippos_desktop_entries import read_desktop_file
import hippos_flatpak_apps
import hippos_quiver
from emulatorlauncher_registry import Emulator, register

_VICE_BORDER_OPTION: dict[str, str] = {
    'x64':     '-VICIIborders',
    'x64sc':   '-VICIIborders',
    'x64dtv':  '-VICIIborders',
    'xscpu64': '-VICIIborders',
    'x128':    '-VICIIborders',
    'xcbm5x0': '-VICIIborders',
    'xvic':    '-VICborders',
    'xplus4':  '-TEDborders',
}
_VICE_BORDER_NONE = '3'

LUTRISVIEW = '/usr/lib/hippos/lutrisview'
LUTRISVIEW_THEME = '/usr/share/emulationstation/themes/es-theme-hippos'

def launch_vice(ctx: LaunchContext) -> int:
    binary = ctx.core or 'x64'
    bin_path = _require_emulator_bin_in_package('vice', binary)
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    from emulatorlauncher_vice_controllers import configure_vice_joysticks
    cmd = [str(bin_path), *configure_vice_joysticks(ctx, binary)]
    border_option = _VICE_BORDER_OPTION.get(binary)
    if border_option and _conf_bool(conf, f'{ctx.system}.noborder'):
        cmd += [border_option, _VICE_BORDER_NONE]
    cmd.append(str(ctx.rom))
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

def launch_simcoupe(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin_in_package('samcoupe', 'samcoupe', 'simcoupe')
    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    cmd = [str(bin_path), 'autoboot', '-disk1', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

def launch_sh(ctx: LaunchContext) -> int:
    if ctx.rom.suffix == '.flatpak':
        return launch_flatpak(ctx)
    rom = ctx.rom
    script = (rom / 'run.sh') if rom.is_dir() and (rom / 'run.sh').exists() else rom
    if not script.exists():
        return 1
    mode = script.stat().st_mode
    if not (mode & 0o111):
        try:
            script.chmod(mode | 0o111)
        except PermissionError:
            pass
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    result = _run_game_command(ctx, ['/bin/bash', str(script)], env,
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
    cmd = hippos_flatpak_apps.run_command(app_id)
    _log.info("Launching Flatpak: %s", app_id)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

CHROMIUM_BROWSERS = frozenset({
    'chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable',
    'brave-browser', 'microsoft-edge', 'microsoft-edge-stable', 'vivaldi', 'vivaldi-stable',
    'org.chromium.Chromium', 'com.google.Chrome', 'com.brave.Browser', 'com.microsoft.Edge', 'com.vivaldi.Vivaldi',
})

def _kiosk_command(command: str) -> str:
    try:
        words = shlex.split(command)
    except ValueError:
        return command
    starts_browser = bool(words) and (Path(words[0]).name in CHROMIUM_BROWSERS
                                      or (Path(words[0]).name == 'flatpak' and CHROMIUM_BROWSERS & set(words)))
    return f'{command} --kiosk' if starts_browser and '--kiosk' not in words else command

def _run_desktop_app(ctx: LaunchContext, cmd: list[str]) -> int:
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    _log.info("Launching %s", ' '.join(cmd))
    return _run_game_command(ctx, cmd, env).returncode

def launch_desktopshortcuts(ctx: LaunchContext) -> int:
    try:
        desktop_file = Path(ctx.rom.read_text(encoding='utf-8').strip())
    except OSError as exc:
        _log.error("Could not read desktop file path from %s: %s", ctx.rom, exc)
        return 1
    app = read_desktop_file(desktop_file)
    if app is None:
        _log.error("No launchable application in %s", desktop_file)
        return 1
    return _run_desktop_app(ctx, ['/bin/sh', '-c', _kiosk_command(app.command)])

def launch_webapp(ctx: LaunchContext) -> int:
    if ctx.rom.suffix == '.flatpak':
        return launch_flatpak(ctx)
    if ctx.rom.suffix == '.sh':
        return launch_sh(ctx)
    from hippos_webapps import ADD_WEBAPP_URL, WEBAPP_PROFILES, WEBAPPS_BIN, read_webapp
    url = read_webapp(ctx.rom)
    if url is None:
        _log.error("No address in %s", ctx.rom)
        return 1
    if url == ADD_WEBAPP_URL:
        return _run_desktop_app(ctx, [str(WEBAPPS_BIN), 'dialog'])
    chromium = which('chromium')
    if chromium is None:
        _log.error("Web apps need Chromium; add one through Linux Apps or the Content Downloader to install it")
        return 1
    profile = WEBAPP_PROFILES / ctx.rom.stem
    profile.mkdir(parents=True, exist_ok=True)
    return _run_desktop_app(ctx, [chromium, f'--app={url}', '--kiosk', f'--user-data-dir={profile}',
                                  '--no-first-run', '--no-default-browser-check'])

def launch_heroic(ctx: LaunchContext) -> int:
    wrapper = Path('/usr/lib/hippos/hippos-heroic')
    if not wrapper.exists():
        _log.error("Heroic wrapper not found: %s", wrapper)
        return 1
    try:
        entry = ctx.rom.read_text(encoding='utf-8').strip()
    except OSError as exc:
        _log.error("Could not read Heroic launcher from %s: %s", ctx.rom, exc)
        return 1
    if not entry:
        _log.error("Empty Heroic launcher in %s", ctx.rom)
        return 1
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    cmd = [str(wrapper), str(ctx.rom)]
    _log.info("Launching Heroic: %s", entry)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

def launch_lutris(ctx: LaunchContext) -> int:
    try:
        target = ctx.rom.read_text(encoding='utf-8').strip()
    except OSError as exc:
        _log.error("Could not read Lutris launcher from %s: %s", ctx.rom, exc)
        return 1
    if target != CLIENT_ENTRY and not target.isdigit():
        _log.error("Not a Lutris game id in %s: %r", ctx.rom, target)
        return 1
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = '/userdata/system/.config'
    env['XDG_DATA_HOME'] = '/userdata/.local/share'
    env['XDG_CACHE_HOME'] = '/userdata/.cache'
    env['PATH'] = f"{env.get('PATH', '')}:/usr/local/games:/usr/games"
    if target == CLIENT_ENTRY:
        env['LUTRISVIEW_THEME'] = LUTRISVIEW_THEME
        cmd = [LUTRISVIEW]
    else:
        cmd = ['lutris', f'lutris:rungameid/{target}']
    _log.info("Launching Lutris: %s", target)
    return _run_game_command(ctx, cmd, env).returncode

def launch_quiver(ctx: LaunchContext) -> int:
    try:
        target = ctx.rom.read_text(encoding='utf-8').strip()
    except OSError as exc:
        _log.error("Could not read Quiver launcher from %s: %s", ctx.rom, exc)
        return 1
    if not target:
        _log.error("Empty Quiver launcher in %s", ctx.rom)
        return 1
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    cmd = list(hippos_quiver.LAUNCH_COMMAND)
    if target != CLIENT_ENTRY:
        cmd += ['--run', target]
    _log.info("Launching Quiver: %s", target)
    return _run_game_command(ctx, cmd, env).returncode

def launch_pygame(ctx: LaunchContext) -> int:
    pygame_dir = Path('/opt/emulators/python-pygame2')
    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    if pygame_dir.exists():
        env['PYTHONPATH'] = str(pygame_dir) + ':' + env.get('PYTHONPATH', '')
        libs = str(pygame_dir / 'pygame.libs')
        env['LD_LIBRARY_PATH'] = libs + ':' + env.get('LD_LIBRARY_PATH', '')
    result = _run_game_command(ctx, ['python3', str(ctx.rom)], env,
                               cwd=ctx.rom.parent)
    return result.returncode

def launch_ruffle(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('ruffle')
    conf = _load_hippos_conf()
    cmd = [str(bin_path), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

def launch_lightspark(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('lightspark')
    conf = _load_hippos_conf()
    cmd = [str(bin_path), '-fs', '-s', 'local-with-networking', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

def launch_pyxel(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('pyxel')
    conf = _load_hippos_conf()
    cmd = [str(bin_path), 'play' if ctx.rom.suffix == '.pyxapp' else 'run', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['PYTHONPATH'] = str(bin_path.parent.parent)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

def _clk_media(rom: Path) -> Path:
    if not zipfile.is_zipfile(rom):
        return rom
    extract_dir = Path('/tmp/clk') / rom.stem
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(rom) as archive:
        archive.extractall(extract_dir)
        return extract_dir / sorted(archive.namelist())[0]

def launch_clk(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('clksignal', 'clk')
    if ctx.rom.is_dir():
        return 1
    conf = _load_hippos_conf()
    cmd: list[str] = [str(bin_path), str(_clk_media(ctx.rom)), '--rompath=/userdata/bios/']
    if ctx.system in CLK_SVIDEO_SYSTEMS:
        cmd.append('--output=SVideo')
    if ctx.system in CLK_RGB_SYSTEMS:
        cmd.append('--output=RGB')
    if ctx.system in CLK_QUICKLOAD_SYSTEMS:
        cmd.append('--accelerate-media-loading')
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

def launch_tsugaru(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('Tsugaru_CUI', 'tsugaru')
    conf = _load_hippos_conf()
    cmd: list[str] = [str(bin_path), str(BIOS / 'fmtowns'), '-FULLSCREEN', '-NOHIGHRESPCM', '-NOWAITBOOT', '-AUTOSCALE', '-MAINTAINASPECT', '-HIGHRES', '-GAMEPORT0', 'KEY', '-KEYBOARD', 'DIRECT', '-PAUSEKEY', 'F10']
    if (cdrom_speed := _game_value(conf, ctx, 'cdrom_speed', 'auto')) != 'auto':
        cmd += ['-CDSPEED', cdrom_speed]
    if _game_bool(conf, ctx, '386dx', False):
        cmd.append('-PRETEND386DX')
    if ctx.rom.suffix.lower() in TSUGARU_CD_SYSTEMS:
        cmd += ['-CD', str(ctx.rom)]
    else:
        cmd += ['-FD0', str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

def launch_x16emu(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('x16emu')
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
    cmd += ['-scale', _game_value(conf, ctx, 'x16emu_scale', '2')]
    if (quality := _game_value(conf, ctx, 'x16emu_quality', '')):
        cmd += ['-quality', quality]
    if _game_value(conf, ctx, 'x16emu_ratio', '') == '16:9':
        cmd.append('-widescreen')
    for nplayer, _ in enumerate(ctx.controllers[:4], start=1):
        cmd.append(f'-joy{nplayer}')
    (SAVES / 'x16').mkdir(parents=True, exist_ok=True)
    env = _build_game_env(conf, ctx)
    env['XDG_DATA_HOME'] = str(SAVES / 'x16')
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

def launch_ioquake3(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('ioquake3')
    if bin_path is None:
        _log.error("ioquake3 not installed")
        return 1
    conf = _load_hippos_conf()
    cmd: list[str] = [str(bin_path)]
    try:
        args = ctx.rom.read_text(encoding='utf-8').strip().split()
        cmd.extend(args)
    except OSError:
        pass
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    result = _run_game_command(ctx, cmd, env, cwd=ctx.rom.parent)
    return result.returncode

def launch_lexaloffle(ctx: LaunchContext) -> int:
    system = ctx.system
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
        if system == 'pico8':
            from emulatorlauncher_generic import launch_libretro
            _log.info("PICO-8 not found at %s; using the retro8 core", bin_path)
            return launch_libretro(replace(ctx, emulator='retroarch', core='retro8'))
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
    result = _run_game_command(ctx, cmd, env)
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
    result = _run_game_command(ctx, cmd, env)
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
        f'res={_game_value(conf, ctx, "redreamResolution", "2")}',
        f'aspect={_game_value(conf, ctx, "redreamRatio", "4:3")}',
        f'frameskip={_game_value(conf, ctx, "redreamFrameSkip", "0")}',
        f'vsync={_game_value(conf, ctx, "redreamVsync", "0")}',
        f'renderer={_game_value(conf, ctx, "redreamRender", "hle_perstrip")}',
        f'region={_game_value(conf, ctx, "redreamRegion", "usa")}',
        f'language={_game_value(conf, ctx, "redreamLanguage", "english")}',
        f'broadcast={_game_value(conf, ctx, "redreamBroadcast", "ntsc")}',
        f'cable={_game_value(conf, ctx, "redreamCable", "vga")}',
    ]
    cfg_file.write_text('\n'.join(lines) + '\n')

    cmd = [str(bin_path), str(ctx.rom)]
    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    env['SDL_AUDIODRIVER']     = 'alsa'
    result = _run_game_command(ctx, cmd, env)
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
    result = _run_game_command(ctx, cmd, env)
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

    gz_api = _conf_value(conf, 'gz_api', '0')
    if gz_api == '3':
        api_cfg = 'gl_es 1\nvid_preferbackend 3\ngles_use_mapped_buffer true\n'
    else:
        api_cfg = f'vid_preferbackend {gz_api}\n'

    show_fps = _conf_bool(conf, 'show_fps', False)
    script_path.write_text(
        f'logfile "{logs_dir / "gzdoom.log"}"\n'
        f'vid_fps {"true" if show_fps else "false"}\n'
        + api_cfg +
        'echo HIPPOS\n',
        encoding='utf-8',
    )

    sections = _gzdoom_read_ini(ini_path)

    _gzdoom_ini_set(sections, '[GlobalSettings]', 'vid_vsync', _conf_value(conf, 'gz_vsync', 'false'))
    _gzdoom_ini_set(sections, '[GlobalSettings]', 'use_joystick', 'true')

    rom_parent = str(ctx.rom.parent)
    for sec in ('[IWADSearch.Directories]', '[FileSearch.Directories]'):
        existing_vals = set(sections.get(sec, {}).values())
        if f'Path={rom_parent}' not in existing_vals:
            idx = len(sections.get(sec, {}))
            _gzdoom_ini_set_if_missing(sections, sec, f'Path_{idx}', rom_parent)

    for p in ['/usr/share/gzdoom/soundfonts', '/usr/share/gzdoom/fm_banks',
              str(cfg_dir / 'soundfonts'), str(cfg_dir / 'fm_banks')]:
        _gzdoom_ini_set_if_missing(sections, '[SoundfontSearch.Directories]', f'Path_{p}', p)

    for bind_sec in ('[Doom.Bindings]', '[Doom.AutomapBindings]'):
        sections.setdefault(bind_sec, {})
        sections[bind_sec] = {k: v for k, v in sections[bind_sec].items()
                               if not k.startswith('Joy')}

    if ctx.controllers:
        p1 = ctx.controllers[0]
        profile = _pick_es_profile(profiles, p1)
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
    result = _run_game_command(ctx, cmd, env, cwd=ctx.rom.parent)
    return result.returncode

CLK_QUICKLOAD_SYSTEMS = {'amstradcpc', 'archimedes', 'electron', 'msx1', 'msx2', 'oricatmos', 'zxspectrum'}
CLK_SVIDEO_SYSTEMS = {'colecovision', 'mastersystem'}
CLK_RGB_SYSTEMS = {'amstradcpc', 'atarist', 'electron', 'enterprise', 'msx1', 'msx2', 'oricatmos', 'zxspectrum'}
TSUGARU_CD_SYSTEMS = {'.iso', '.cue', '.bin'}

register(Emulator('sh', launch_sh, writes_to_rom=True, hud_wrapper=True, hotkeys='shell'))
register(Emulator('python-pygame2', launch_pygame, hotkeys='pygame'))
register(Emulator('python-pyxel', launch_pyxel, hotkeys='pyxel'))
register(Emulator('corsixth', launch_corsixth))
register(Emulator('flatpak', launch_flatpak, binaries=('flatpak',), hud_wrapper=True))
register(Emulator('desktopshortcuts', launch_desktopshortcuts, hotkeys='shell'))
register(Emulator('webapp', launch_webapp, hotkeys='shell'))
register(Emulator('heroic', launch_heroic, binaries=('heroic',)))
register(Emulator('lutris', launch_lutris))
register(Emulator('quiver', launch_quiver))
register(Emulator('clk', launch_clk, binaries=('clksignal', 'clk')))
register(Emulator('gzdoom', launch_gzdoom))
register(Emulator('lightspark', launch_lightspark, binaries=('lightspark',)))
register(Emulator('pyxel', launch_pyxel, binaries=('pyxel',), packages=('python-pyxel',), writes_to_rom=True))
register(Emulator('pygame', launch_pygame, writes_to_rom=True))
register(Emulator('ruffle', launch_ruffle, binaries=('ruffle',)))
register(Emulator('samcoupe', launch_simcoupe, binaries=('samcoupe', 'simcoupe')))
register(Emulator('tsugaru', launch_tsugaru, binaries=('Tsugaru_CUI', 'tsugaru')))
register(Emulator('x16emu', launch_x16emu, binaries=('x16emu',)))
register(Emulator('redream', launch_redream, binaries=('redream',)))
register(Emulator('vice', launch_vice, binaries=('x64', 'x64sc', 'xscpu64', 'xvic', 'x128', 'x64dtv', 'xplus4', 'xpet')))
register(Emulator('ioquake3', launch_ioquake3))
register(Emulator('lexaloffle', launch_lexaloffle))
register(Emulator('lexaloffle-pico8', launch_lexaloffle))
register(Emulator('lexaloffle-voxatron', launch_lexaloffle))
register(Emulator('uqm', launch_uqm))
