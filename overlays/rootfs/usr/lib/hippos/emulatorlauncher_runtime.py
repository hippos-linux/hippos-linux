from __future__ import annotations

from pathlib import Path

from emulatorlauncher_impl import (
    AMIBERRY_BIOS_DIR,
    AMIBERRY_CONFIG_DIR,
    AMIBERRY_CONF,
    AMIBERRY_DATA_DIR,
    AMIBERRY_INPUTS_DIR,
    AMIBERRY_LOG_FILE,
    AMIBERRY_OVERLAY_CFG,
    AMIBERRY_PLUGINS_DIR,
    AMIBERRY_RETROARCH_DIR,
    AMIBERRY_SAVES_DIR,
    AMIBERRY_SCREENSHOTS_DIR,
    AMIBERRY_WHDBOOT_DIR,
    CONFIGS,
    LINDBERGH_CONFIG_DIR,
    LINDBERGH_CONFIG_FILE,
    LINDBERGH_CONTROLS_FILE,
    LINDBERGH_RUNTIME_DIR,
    LINDBERGH_SAVES_DIR,
    LaunchContext,
    SAVES,
    USERDATA,
    _HAT_DIR,
    _RA_BTN_MAP,
    _RA_DPAD_MAP,
    _RA_AXIS_MAP,
    _amiberry_rom_type,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _display_resolution_from_conf,
    _ensure_section,
    _find_emulator_bin,
    _find_executable,
    _load_effective_hippos_conf,
    _load_es_input_configs,
    _load_hippos_conf,
    _lindbergh_binding_to_value,
    _lindbergh_game_section,
    _lindbergh_mapping_for_device,
    _lindbergh_short_rom_name,
    _lindbergh_write_templates,
    _new_ini_parser,
    _pick_es_profile,
    _ra_analog_dpad_mode,
    _ra_binding_value,
    _ra_btn_map_for_ctx,
    _ra_type_suffix,
    _run_game_command,
    _sync_tree,
    _write_unix_settings_file,
    generate_sdl_game_controller_config,
)


def _amiberry_floppies_from_rom(rom: Path) -> list[Path]:
    floppies: list[Path] = []
    index_disk = rom.name.rfind('(Disk 1')
    if rom.stem[-1:].isdigit():
        fileprefix = rom.stem[:-1]
        zero_file = rom.with_name(f'{fileprefix}0{rom.suffix}')
        if zero_file.is_file():
            floppies.append(zero_file)
        n = 1
        while (floppy := rom.with_name(f'{fileprefix}{n}{rom.suffix}')).is_file():
            floppies.append(floppy)
            n += 1
    elif index_disk != -1:
        floppies.append(rom)
        prefix = rom.name[0:index_disk + 6]
        postfix = rom.name[index_disk + 7:]
        n = 2
        while (floppy := rom.with_name(f'{prefix}{n}{postfix}')).is_file():
            floppies.append(floppy)
            n += 1
    else:
        return [rom]
    return floppies


def _write_amiberry_retroarch_config(ctx: LaunchContext) -> None:
    """Write retroarch overlay.cfg + per-pad .cfg files for Amiberry."""
    AMIBERRY_RETROARCH_DIR.mkdir(parents=True, exist_ok=True)
    AMIBERRY_INPUTS_DIR.mkdir(parents=True, exist_ok=True)

    profiles = _load_es_input_configs()
    lines: list[str] = []

    for ctrl in ctx.controllers:
        profile = _pick_es_profile(profiles, ctrl)
        if profile is None:
            continue
        n       = ctrl.player
        system  = ctx.system
        core    = ctx.core or ''
        btn_map = _ra_btn_map_for_ctx(profile, system, core, '')

        lines.append(f'input_player{n}_joypad_index = "{ctrl.index}"')

        for es_name, ra_name in btn_map.items():
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            suffix = _ra_type_suffix(binding)
            lines.append(f'input_player{n}_{ra_name}_{suffix} = "{_ra_binding_value(binding)}"')

        for es_name, ra_dpad in _RA_DPAD_MAP:
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            suffix = _ra_type_suffix(binding)
            lines.append(f'input_player{n}_{ra_dpad}_{suffix} = "{_ra_binding_value(binding)}"')

        for es_name, ra_base in _RA_AXIS_MAP:
            binding = profile.inputs.get(es_name)
            if binding is None or binding.type != 'axis':
                continue
            primary_sign  = '-' if binding.value < 0 else '+'
            opposite_sign = '+' if primary_sign == '-' else '-'
            lines.append(f'input_player{n}_{ra_base}_minus_axis = "{primary_sign}{binding.code}"')
            lines.append(f'input_player{n}_{ra_base}_plus_axis = "{opposite_sign}{binding.code}"')

        lines.append(f'input_player{n}_analog_dpad_mode = "{_ra_analog_dpad_mode(profile, system)}"')

    overlay_text = '\n'.join(lines) + '\n'
    AMIBERRY_OVERLAY_CFG.write_text(overlay_text, encoding='utf-8')

    # Write per-pad cfg file (with player prefix stripped) for Amiberry's controller path
    for ctrl in ctx.controllers:
        padfilename = ctrl.name.replace('/', '')
        per_pad_cfg = AMIBERRY_INPUTS_DIR / f'{padfilename}.cfg'
        n = ctrl.player
        pad_lines = [
            line.replace(f'input_player{n}_', 'input_player_')
            for line in overlay_text.splitlines()
            if f'input_player{n}_' in line
        ]
        per_pad_cfg.write_text('\n'.join(pad_lines) + '\n', encoding='utf-8')


def launch_amiberry(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    rom_type = _amiberry_rom_type(ctx.rom)

    for path in (AMIBERRY_CONFIG_DIR, AMIBERRY_RETROARCH_DIR, AMIBERRY_INPUTS_DIR, AMIBERRY_PLUGINS_DIR, AMIBERRY_WHDBOOT_DIR):
        path.mkdir(parents=True, exist_ok=True)
    AMIBERRY_SAVES_DIR.mkdir(parents=True, exist_ok=True)
    AMIBERRY_BIOS_DIR.mkdir(parents=True, exist_ok=True)

    _write_unix_settings_file(AMIBERRY_CONF, [
        ('default_quit_key', 'F9'),
        ('default_open_gui_key', 'F8'),
        ('saveimage_dir', AMIBERRY_SAVES_DIR),
        ('savestate_dir', AMIBERRY_SAVES_DIR),
        ('screenshot_dir', AMIBERRY_SCREENSHOTS_DIR),
        ('nvram_dir', AMIBERRY_SAVES_DIR / 'nvram'),
        ('rom_path', AMIBERRY_BIOS_DIR),
        ('whdboot_path', AMIBERRY_WHDBOOT_DIR),
        ('logfile_path', AMIBERRY_LOG_FILE),
        ('controllers_path', AMIBERRY_INPUTS_DIR),
        ('retroarch_config', AMIBERRY_OVERLAY_CFG),
        ('default_vkbd_enabled', '1' if _conf_bool(conf, 'amiberry_virtual_keyboard', False) else '0'),
        ('default_vkbd_hires', '1' if _conf_bool(conf, 'amiberry_hires_keyboard', False) else '0'),
        ('default_vkbd_transparency', _conf_value(conf, 'amiberry_vkbd_transparency', '60')),
        ('default_vkbd_language', _conf_value(conf, 'amiberry_vkbd_language', 'US')),
        ('default_vkbd_toggle', 'leftstick'),
        ('default_fullscreen_mode', '2'),
        ('write_logfile', 'yes'),
    ])
    # Write retroarch controller config + per-pad input files
    _write_amiberry_retroarch_config(ctx)

    # SDL controller DB for Amiberry's retroarch input path
    db_path = AMIBERRY_INPUTS_DIR / 'gamecontrollerdb.txt'
    db_path.write_text(generate_sdl_game_controller_config(ctx.controllers))

    commandArray: list[str | Path] = [str(_find_emulator_bin('amiberry') or 'amiberry')]
    if rom_type != 'WHDL':
        commandArray += ['--model', ctx.core]
    if rom_type == 'WHDL':
        commandArray += ['--autoload', ctx.rom]
    elif rom_type == 'HDF':
        commandArray += ['-s', f'hardfile2=rw,DH0:{ctx.rom},32,1,2,512,0,,uae0', '-s', f'uaehf0=hdf,rw,DH0:{ctx.rom},32,1,2,512,0,,uae0']
    elif rom_type == 'UAE':
        commandArray += ['-f', ctx.rom]
    elif rom_type == 'CD':
        commandArray += ['--cdimage', ctx.rom]
    elif rom_type == 'DISK':
        for n, img in enumerate(_amiberry_floppies_from_rom(ctx.rom)[:4]):
            commandArray += [f'-{n}', img]
        commandArray += ['-s', f'amiberry.floppy_path={ctx.rom.parent}']

    if ctx.controllers:
        for pad in ctx.controllers:
            padfilename = pad.name.replace('/', '')
            if pad.player == 1:
                commandArray += ['-s', f'joyport1_friendlyname={padfilename}']
                if rom_type == 'CD':
                    commandArray += ['-s', 'joyport1_mode=cd32joy']
            if pad.player == 2:
                commandArray += ['-s', f'joyport0_friendlyname={padfilename}']
        commandArray += ['-s', 'joyport2=']
    else:
        commandArray += ['-s', 'joyport2=']

    commandArray += ['-s', f'gfx_flickerfixer={"true" if _conf_bool(conf, "amiberry_flickerfixer", False) else "false"}']
    commandArray += ['-s', f'amiberry.gfx_auto_height={"true" if _conf_bool(conf, "amiberry_auto_height", False) else "false"}']
    commandArray += ['-s', f'gfx_linemode={_conf_value(conf, "amiberry_linemode", "double")}']
    commandArray += ['-s', f'gfx_resolution={_conf_value(conf, "amiberry_resolution", "hires")}']

    match _conf_value(conf, 'amiberry_scalingmethod', ''):
        case 'smooth':
            commandArray += ['-s', 'gfx_lores_mode=true', '-s', 'amiberry.scaling_method=1']
        case 'pixelated':
            commandArray += ['-s', 'gfx_lores_mode=true', '-s', 'amiberry.scaling_method=0']
        case _:
            commandArray += ['-s', 'gfx_lores_mode=false', '-s', 'amiberry.scaling_method=-1']

    commandArray += ['-s', 'gfx_center_vertical=smart', '-s', 'sound_max_buff=4096', '-s', 'sound_frequency=48000', '-G']

    _log = __import__('logging').getLogger('hippos.emulatorlauncher')
    _log.info("Launching Amiberry: %s", ' '.join(map(str, commandArray)))
    env = _build_game_env(conf, ctx)
    env.update({
        'AMIBERRY_DATA_DIR': str(AMIBERRY_DATA_DIR),
        'AMIBERRY_HOME_DIR': str(AMIBERRY_CONFIG_DIR),
        'AMIBERRY_CONFIG_DIR': str(AMIBERRY_CONFIG_DIR),
        'AMIBERRY_PLUGINS_DIR': str(AMIBERRY_PLUGINS_DIR),
        'XDG_DATA_HOME': str(CONFIGS),
        'XDG_CONFIG_HOME': str(CONFIGS),
        'SDL_GAMECONTROLLERCONFIG': generate_sdl_game_controller_config(ctx.controllers),
        'SDL_JOYSTICK_HIDAPI': '0',
    })
    result = _run_game_command(ctx, 'amiberry', commandArray, env)
    return result.returncode


def _solarus_key_val(binding, reverse: bool = False) -> str:
    """Convert ES binding to Solarus pads.ini value string."""
    if binding.type == 'button':
        return f'button {binding.code}'
    if binding.type == 'hat':
        dirs = {1: 'up', 2: 'right', 4: 'down', 8: 'left'}
        return f'hat 0 {dirs.get(abs(binding.value), "up")}'
    if binding.type == 'axis':
        if (reverse and binding.value < 0) or (not reverse and binding.value > 0):
            return f'axis {binding.code} +'
        return f'axis {binding.code} -'
    return ''


def launch_solarus(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('solarus-run', 'solarus')
    if bin_path is None:
        return 1
    conf = _load_hippos_conf()
    config_dir = CONFIGS / 'solarus'
    config_dir.mkdir(parents=True, exist_ok=True)

    # Build pads.ini with full key mappings for P1
    keymapping = {
        'action': 'a',    'attack': 'b',    'item1': 'y',  'item2': 'x',
        'pause':  'start',
        'right':  'right', 'up': 'up', 'left': 'left', 'down': 'down',
    }
    reverse_axis = {'up': 'down', 'left': 'right'}

    profiles = _load_es_input_configs()
    pads_file = config_dir / 'pads.ini'
    with pads_file.open('w', encoding='ascii') as fh:
        p1 = next((c for c in ctx.controllers if c.player == 1), None)
        if p1:
            profile = _pick_es_profile(profiles, p1)
            if profile:
                for key, es_name in keymapping.items():
                    binding = profile.inputs.get(es_name)
                    if binding is None:
                        continue
                    fh.write(f'{key}={_solarus_key_val(binding, False)}\n')
                    if key in reverse_axis and binding.type == 'axis':
                        fh.write(f'{reverse_axis[key]}={_solarus_key_val(binding, True)}\n')

    cmd: list[str] = [str(bin_path), '-fullscreen=yes', '-cursor-visible=no', '-lua-console=no']
    for nplayer, ctrl in enumerate(ctx.controllers, start=1):
        if nplayer == 1:
            p1_profile = _pick_es_profile(profiles, ctrl) if profiles else None
            hotkey = p1_profile.inputs.get('hotkey') if p1_profile else None
            start  = p1_profile.inputs.get('start')  if p1_profile else None
            if hotkey and start:
                cmd.append(f'-quit-combo={hotkey.code}+{start.code}')
            else:
                cmd.append('-quit-combo=0+1')
        cmd.append(f'-joypad-num{nplayer}={ctrl.index}')
    cmd.append(str(ctx.rom))
    _log = __import__('logging').getLogger('hippos.emulatorlauncher')
    _log.info("Launching solarus: %s", ' '.join(cmd))
    env = _build_game_env(conf, ctx)
    env['SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS'] = '0'
    result = _run_game_command(ctx, 'solarus', cmd, env)
    return result.returncode


def launch_steam(ctx: LaunchContext) -> int:
    game_id = ''
    big_picture = ctx.rom.name == 'Steam.steam'
    if not big_picture:
        try:
            game_id = ctx.rom.read_text(encoding='utf-8').strip()
        except OSError as exc:
            __import__('logging').getLogger('hippos.emulatorlauncher').error("Could not read Steam app id from %s: %s", ctx.rom, exc)
            return 1

    wrapper = Path('/usr/lib/hippos/hippos-steam')
    if not wrapper.exists():
        __import__('logging').getLogger('hippos.emulatorlauncher').error("Steam wrapper not found: %s", wrapper)
        return 1

    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)

    cmd = [str(wrapper)]
    if big_picture:
        cmd.append('--big-picture')
    if game_id:
        cmd.extend(['-applaunch', game_id])

    _log = __import__('logging').getLogger('hippos.emulatorlauncher')
    _log.info("Launching Steam: %s", ' '.join(cmd))
    result = _run_game_command(ctx, 'steam', cmd, env)
    return result.returncode


def launch_wine(ctx: LaunchContext) -> int:
    wrapper = Path('/usr/lib/hippos/hippos-wine')
    if not wrapper.exists():
        __import__('logging').getLogger('hippos.emulatorlauncher').error("Wine wrapper not found: %s", wrapper)
        return 1

    mode = 'play'
    if ctx.system == 'windows_installers':
        ext = ctx.rom.suffix.lower().lstrip('.')
        if ext not in ('exe', 'iso', 'msi'):
            __import__('logging').getLogger('hippos.emulatorlauncher').error("Unsupported Windows installer type: %s", ctx.rom)
            return 1
        mode = 'install'
    elif ctx.system != 'windows':
        __import__('logging').getLogger('hippos.emulatorlauncher').error("Wine launcher used for unsupported system '%s'", ctx.system)
        return 1

    conf = _load_hippos_conf()
    env = _build_game_env(conf, ctx)
    if ctx.core and ctx.core not in ('wine', 'wine-default'):
        env['HIPPOS_RUNNER'] = ctx.core
    cmd = [str(wrapper), ctx.system, mode, str(ctx.rom)]
    __import__('logging').getLogger('hippos.emulatorlauncher').info("Launching Wine: %s", ' '.join(cmd))
    result = _run_game_command(ctx, 'wine', cmd, env)
    return result.returncode


def launch_lindbergh_loader(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('lindbergh-loader')
    if bin_path is None:
        __import__('logging').getLogger('hippos.emulatorlauncher').error("lindbergh-loader not found")
        return 1

    payload_root = bin_path.parent.parent if bin_path.parent.name == 'bin' else bin_path.parent
    LINDBERGH_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if payload_root.exists():
        _sync_tree(payload_root, LINDBERGH_RUNTIME_DIR)

    runtime_exec = _find_executable(LINDBERGH_RUNTIME_DIR)
    if runtime_exec is None:
        runtime_exec = bin_path
    if not runtime_exec.exists():
        __import__('logging').getLogger('hippos.emulatorlauncher').error("lindbergh-loader executable not found")
        return 1

    conf = _load_hippos_conf()
    profiles = _load_es_input_configs()
    short_rom = _lindbergh_short_rom_name(ctx.rom)
    controller_mode = _conf_value(conf, 'lindbergh_controller', '2')
    input_mode = 1 if controller_mode == '1' else 2
    game_section = _lindbergh_game_section(short_rom)

    LINDBERGH_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ini_parser, controls_parser = _lindbergh_write_templates()

    _ensure_section(ini_parser, 'Display')
    _ensure_section(ini_parser, 'Input')
    _ensure_section(ini_parser, 'Emulation')
    _ensure_section(ini_parser, 'Paths')
    _ensure_section(ini_parser, 'Graphics')
    _ensure_section(ini_parser, 'Cursor')
    _ensure_section(ini_parser, 'GameSpecific')
    _ensure_section(ini_parser, 'CrossHairs')
    _ensure_section(ini_parser, 'System')
    _ensure_section(ini_parser, 'Network')
    _ensure_section(ini_parser, 'EVDEV')

    resolution = _display_resolution_from_conf(conf)
    width = str(resolution[0]) if resolution else 'AUTO'
    height = str(resolution[1]) if resolution else 'AUTO'
    ini_parser.set('Display', 'WIDTH', width)
    ini_parser.set('Display', 'HEIGHT', height)
    ini_parser.set('Display', 'FULLSCREEN', 'true')
    ini_parser.set('Display', 'BORDER_ENABLED', 'true' if _conf_bool(conf, 'global.use_guns', False) or ctx.lightgun else 'false')
    ini_parser.set('Display', 'KEEP_ASPECT_RATIO', 'true' if _conf_bool(conf, 'lindbergh_aspect', True) else 'false')
    ini_parser.set('Display', 'HIDE_CURSOR', 'true' if _conf_bool(conf, 'lindbergh_hide_cursor', True) else 'false')
    ini_parser.set('Display', 'BOOST_RENDER_RES', 'true' if _conf_bool(conf, 'lindbergh_boost', False) else 'false')
    ini_parser.set('Input', 'INPUT_MODE', '1' if input_mode == 1 else '2')
    ini_parser.set('Emulation', 'REGION', _conf_value(conf, 'lindbergh_region', 'EX') or 'EX')
    ini_parser.set('Emulation', 'FREEPLAY', 'true' if _conf_bool(conf, 'lindbergh_freeplay', False) else 'false')
    ini_parser.set('Emulation', 'EMULATE_JVS', 'true')
    ini_parser.set('Emulation', 'EMULATE_RIDEBOARD', 'AUTO')
    ini_parser.set('Emulation', 'EMULATE_DRIVEBOARD', 'true' if _conf_bool(conf, 'lindbergh_ffb', True) else 'auto')
    ini_parser.set('Emulation', 'EMULATE_MOTIONBOARD', 'AUTO')
    ini_parser.set('Emulation', 'EMULATE_HW210_CARDREADER', 'true' if _conf_bool(conf, 'lindbergh_card', True) and ('tennis' in short_rom or 'rtuned' in short_rom) else 'false')
    ini_parser.set('Emulation', 'EMULATE_ID_CARD READER', 'true' if _conf_bool(conf, 'lindbergh_card', True) and 'initiad' in short_rom else 'false')
    ini_parser.set('Emulation', 'EMULATE_TOUCHSCREEN', 'true' if 'primevah' in short_rom or 'primehunt' in short_rom else 'AUTO')
    ini_parser.set('Paths', 'SRAM_PATH', f'"{LINDBERGH_SAVES_DIR / f"sram.bin.{short_rom}"}"')
    ini_parser.set('Paths', 'EEPROM_PATH', f'"{LINDBERGH_SAVES_DIR / f"eeprom.bin.{short_rom}"}"')
    ini_parser.set('Paths', 'LIBCG_PATH', '')
    ini_parser.set('Graphics', 'GPU_VENDOR', '0')
    ini_parser.set('Graphics', 'HUMMER_FLICKER_FIX', 'true' if _conf_bool(conf, 'lindbergh_hummer', False) else 'false')
    ini_parser.set('Graphics', 'FPS_LIMITER_ENABLED', 'true' if _conf_bool(conf, 'lindbergh_limit', True) else 'false')
    ini_parser.set('Graphics', 'FPS_TARGET', _conf_value(conf, 'lindbergh_fps', '60.0') or '60.0')
    ini_parser.set('Graphics', 'LGJ_RENDER_WITH_MESA', 'true')
    ini_parser.set('Graphics', 'DISABLE_BUILTIN_FONT', 'true' if _conf_bool(conf, 'lindbergh_disable_font', False) else 'false')
    ini_parser.set('Graphics', 'DISABLE_BUILTIN_LOGOS', 'true' if _conf_bool(conf, 'lindbergh_disable_logos', False) else 'false')
    ini_parser.set('Cursor', 'CUSTOM_CURSOR_ENABLED', 'false')
    ini_parser.set('Cursor', 'CUSTOM_CURSOR', '')
    ini_parser.set('Cursor', 'TOUCH_CURSOR', '')
    ini_parser.set('GameSpecific', 'PRIMEVAL_HUNT_SCREEN_MODE', _conf_value(conf, 'lindbergh_hunt', '1') or '1')
    ini_parser.set('GameSpecific', 'PRIMEVAL_HUNT_TEST_SCREEN_SINGLE', 'true')
    ini_parser.set('GameSpecific', 'SKIP_OUTRUN_CABINET_CHECK', 'true' if _conf_bool(conf, 'lindbergh_cabinet_skip', False) else 'false')
    ini_parser.set('GameSpecific', 'OUTRUN_LENS_GLARE_ENABLED', 'true' if _conf_bool(conf, 'lindbergh_lens', True) else 'false')
    ini_parser.set('GameSpecific', 'MJ4_ENABLED_ALL_THE_TIME', 'false')
    ini_parser.set('GameSpecific', 'CPU_FREQ_GHZ', _conf_value(conf, 'lindbergh_speed', '0.0') or '0.0')
    ini_parser.set('GameSpecific', 'RAMBO_GUNS_SWITCH', 'true' if _conf_bool(conf, 'lindbergh_rambo_switch', False) else 'false')
    ini_parser.set('GameSpecific', 'ID5_CHINESE_LANGUAGE', 'false')
    ini_parser.set('GameSpecific', 'ID_STEERING_REDUCTION_PERCENTAGE', '0.0')
    ini_parser.set('CrossHairs', 'ENABLE_CROSSHAIRS', 'true' if _conf_bool(conf, 'lindbergh_crosshairs', False) or ctx.lightgun else 'false')
    ini_parser.set('CrossHairs', 'P1_CROSSHAIR_PATH', '/usr/bin/lindbergh/crosshairs/p1_crosshair.png' if _conf_bool(conf, 'lindbergh_crosshairs', False) or ctx.lightgun else '')
    ini_parser.set('CrossHairs', 'P2_CROSSHAIR_PATH', '/usr/bin/lindbergh/crosshairs/p2_crosshair.png' if _conf_bool(conf, 'lindbergh_crosshairs', False) or ctx.lightgun else '')
    ini_parser.set('CrossHairs', 'CUSTOM_CROSSHAIRS_WIDTH', '64')
    ini_parser.set('CrossHairs', 'CUSTOM_CROSSHAIRS_HEIGHT', '64')
    ini_parser.set('System', 'DEBUG_MSGS', 'true' if _conf_bool(conf, 'lindbergh_debug', False) else 'false')
    ini_parser.set('System', 'LINDBERGH_COLOUR', 'YELLOW')
    ini_parser.set('Network', 'ENABLE_NETWORK_PATCHES', 'true' if _conf_bool(conf, 'lindbergh_network_patches', True) else 'false')

    _ensure_section(controls_parser, 'Config')
    _ensure_section(controls_parser, 'Common')
    controls_parser.set('Config', 'Steer_DeadZone', '800' if 'initiad' in short_rom else '1000')
    if _conf_bool(conf, 'lindbergh_test', False):
        controls_parser.set('Common', 'Test', 'KEY_T, GC0_BUTTON_A, JOY0_BUTTON_0')
        controls_parser.set('Common', 'P1_Service', 'KEY_S, GC0_BUTTON_DPDOWN, JOY0_HAT0_DOWN')
    else:
        controls_parser.set('Common', 'Test', 'KEY_T')
        controls_parser.set('Common', 'P1_Service', 'KEY_S, JOY0_BUTTON_10, GC0_BUTTON_BACK')

    if input_mode == 2:
        _ensure_section(ini_parser, 'ControllerGUIDs')
        no_player_button = {
            'TEST_BUTTON': True,
            'ANALOGUE_1': True,
            'ANALOGUE_2': True,
            'ANALOGUE_3': True,
            'ANALOGUE_4': True,
            'ANALOGUE_5': True,
            'ANALOGUE_6': True,
            'ANALOGUE_7': True,
            'ANALOGUE_8': True,
        }
        for ctrl in ctx.controllers[:2]:
            profile = _pick_es_profile(profiles, ctrl)
            if profile is None:
                __import__('logging').getLogger('hippos.emulatorlauncher').warning("No ES input profile matched controller %s (%s)", ctrl.name, ctrl.guid)
                continue
            ini_parser.set('ControllerGUIDs', f'P{ctrl.player}_GUID', ctrl.guid or ctrl.device_path or ctrl.name)
            device_type = 'gun' if ctx.lightgun else ('wheel' if ctx.wheel or ctrl.is_wheel else 'pad')
            mapping = _lindbergh_mapping_for_device(short_rom, device_type, ctrl.is_wheel)
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
                player_target = ctrl.player
                if target.endswith('_ON_PLAYER_2'):
                    target = target[:-12]
                    player_target = 2
                if target == 'COIN' and ctrl.player > 1:
                    continue
                if target in no_player_button:
                    if ctrl.player == 1:
                        ini_parser.set('EVDEV', target, value)
                    continue
                if target.startswith('ANALOGUE_'):
                    if ctrl.player == 1:
                        ini_parser.set('EVDEV', target, value)
                    continue
                ini_parser.set('EVDEV', f'PLAYER_{player_target}_{target}', value)

    LINDBERGH_SAVES_DIR.mkdir(parents=True, exist_ok=True)
    with LINDBERGH_CONFIG_FILE.open('w', encoding='utf-8') as fh:
        ini_parser.write(fh, space_around_delimiters=True)
    with LINDBERGH_CONTROLS_FILE.open('w', encoding='utf-8') as fh:
        controls_parser.write(fh, space_around_delimiters=True)

    cmd: list[str] = [str(runtime_exec), '-c', str(LINDBERGH_CONFIG_FILE), '-o', str(LINDBERGH_CONTROLS_FILE), '-g', str(ctx.rom.parent)]
    if _conf_bool(conf, 'lindbergh_zink', False):
        cmd.append('--zink')
    if _conf_bool(conf, 'lindbergh_test', False):
        cmd.append('-t')
    _log = __import__('logging').getLogger('hippos.emulatorlauncher')
    _log.info("Launching lindbergh-loader: %s", ' '.join(cmd))

    env = _build_game_env(conf, ctx)
    env['HOME'] = str(USERDATA / 'system')
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    env['SDL_AUDIODRIVER'] = 'alsa'
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    lib_dir = LINDBERGH_RUNTIME_DIR / 'lib'
    env['LD_LIBRARY_PATH'] = f'/lib32:/lib32/extralibs:/lib:/usr/lib:{runtime_exec.parent}:{lib_dir}:{ctx.rom.parent}'
    preload = next(
        (p for p in (runtime_exec.parent / 'lindbergh.so', lib_dir / 'lindbergh.so') if p.exists()),
        None,
    )
    if preload is not None:
        env['LD_PRELOAD'] = str(preload)
    env['GST_PLUGIN_SYSTEM_PATH_1_0'] = '/lib32/gstreamer-1.0:/usr/lib/gstreamer-1.0'
    env['GST_REGISTRY_1_0'] = f'{USERDATA}/system/.cache/gstreamer-1.0/registry..bin:{USERDATA}/system/.cache/gstreamer-1.0/registry.x86_64.bin'
    env['LIBGL_DRIVERS_PATH'] = '/lib32/dri:/usr/lib/dri'
    env['SPA_PLUGIN_DIR'] = '/lib32/spa-0.2:/usr/lib/spa-0.2'
    env['PIPEWIRE_MODULE_DIR'] = '/lib32/pipewire-0.3:/usr/lib/pipewire-0.3'
    if _conf_bool(conf, 'lindbergh_zink', False):
        env['MESA_LOADER_DRIVER_OVERRIDE'] = 'zink'
        env['VK_LOADER_LAYERS_DISABLE'] = '~all~'

    result = _run_game_command(ctx, 'lindbergh-loader', cmd, env, cwd=LINDBERGH_RUNTIME_DIR)
    return result.returncode
