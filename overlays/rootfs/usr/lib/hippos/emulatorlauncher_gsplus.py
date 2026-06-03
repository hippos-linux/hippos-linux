from __future__ import annotations

from emulatorlauncher_impl import (
    BIOS,
    GSPLUS_CONFIG_DIR,
    GSPLUS_CONFIG_FILE,
    LaunchContext,
    _build_game_env,
    _conf_value,
    _find_emulator_bin,
    _load_hippos_conf,
    _run_game_command,
    _write_unix_settings_file,
    generate_sdl_game_controller_config,
)


def write_gsplus_config(ctx: LaunchContext) -> None:
    conf = _load_hippos_conf()
    GSPLUS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    items: list[tuple[str, object]]
    if ctx.rom.suffix.lower() in ['.dsk', '.do', '.nib']:
        items = [
            ('s6d1', ctx.rom),
            ('s5d1', ''),
            ('s7d1', ''),
            ('bram1[00]', '00 00 00 01 00 00 0d 06 02 01 01 00 01 00 00 00'),
            ('bram1[10]', '00 00 07 06 02 01 01 00 00 00 0f 06 06 00 05 06'),
            ('bram1[20]', '01 00 00 00 00 00 00 01 00 00 00 00 03 02 02 02'),
            ('bram1[30]', '00 00 00 00 00 00 00 00 08 00 01 02 03 04 05 06'),
            ('bram1[40]', '07 0a 00 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d'),
            ('bram1[50]', '0e 0f ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[60]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[70]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[80]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[90]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[a0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[b0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[c0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[d0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[e0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[f0]', 'ff ff ff ff ff ff ff ff ff ff ff ff fe 17 54 bd'),
            ('bram3[00]', '00 00 00 01 00 00 0d 06 02 01 01 00 01 00 00 00'),
            ('bram3[10]', '00 00 07 06 02 01 01 00 00 00 0f 06 00 00 05 06'),
            ('bram3[20]', '01 00 00 00 00 00 00 01 00 00 00 00 05 02 02 00'),
            ('bram3[30]', '00 00 2d 2d 00 00 00 00 00 00 02 02 02 06 08 00'),
            ('bram3[40]', '01 02 03 04 05 06 07 0a 00 01 02 03 04 05 06 07'),
            ('bram3[50]', '08 09 0a 0b 0c 0d 0e 0f 00 00 ff ff ff ff ff ff'),
            ('bram3[60]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram3[70]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram3[80]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram3[90]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram3[a0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram3[b0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram3[c0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram3[d0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram3[e0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram3[f0]', 'ff ff ff ff ff ff ff ff ff ff ff ff 05 cf af 65'),
            ('g_limit_speed', '1'),
        ]
    else:
        items = [
            ('s7d1', ctx.rom),
            ('s5d1', ''),
            ('s6d1', ''),
            ('bram1[00]', '00 00 00 01 00 00 0d 06 02 01 01 00 01 00 00 00'),
            ('bram1[10]', '00 00 07 06 02 01 01 00 00 00 0f 06 06 00 05 06'),
            ('bram1[20]', '01 00 00 00 00 00 00 01 00 00 00 00 03 02 02 02'),
            ('bram1[30]', '00 00 00 00 00 00 00 00 08 00 01 02 03 04 05 06'),
            ('bram1[40]', '07 0a 00 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d'),
            ('bram1[50]', '0e 0f ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[60]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[70]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[80]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[90]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[a0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[b0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[c0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[d0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[e0]', 'ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff ff'),
            ('bram1[f0]', 'ff ff ff ff ff ff ff ff ff ff ff ff 13 24 b9 8e'),
            ('bram3[00]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[10]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[20]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[30]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[40]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[50]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[60]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[70]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[80]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[90]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[a0]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[b0]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[c0]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[d0]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[e0]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('bram3[f0]', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00'),
            ('g_limit_speed', '2'),
        ]

    items.append(('g_cfg_rom_path', BIOS / _conf_value(conf, 'gsplus_bios_filename', 'ROM.03')))
    _write_unix_settings_file(GSPLUS_CONFIG_FILE, items)


def launch_gsplus(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('GSplus', 'gsplus')
    if bin_path is None:
        return 1

    write_gsplus_config(ctx)
    conf = _load_hippos_conf()
    cmd = [str(bin_path), '-fullscreen']
    env = _build_game_env(conf, ctx)
    env['SDL_GAMECONTROLLERCONFIG'] = generate_sdl_game_controller_config(ctx.controllers)
    result = _run_game_command(ctx, 'gsplus', cmd, env)
    return result.returncode
