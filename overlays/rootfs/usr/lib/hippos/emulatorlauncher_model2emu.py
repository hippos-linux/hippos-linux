from __future__ import annotations

import re
from pathlib import Path

from emulatorlauncher_impl import (
    LaunchContext,
    MODEL2_ROMS,
    MODEL2_RUNTIME_EMU,
    MODEL2_RUNTIME_ROOT,
    MODEL2_SOURCE_EMU,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _display_resolution_from_conf,
    _find_emulator_bin,
    _load_effective_hippos_conf,
    _new_ini_parser,
    _run_game_command,
    _sync_tree,
)


def _model2_border_thickness(width: int) -> str:
    if width <= 640:
        return '1'
    if width <= 1080:
        return '2'
    return '3'


def _modify_lua_model2_sinden(file_path: Path, enabled: bool, thickness: str) -> None:
    try:
        lines = file_path.read_text(encoding='utf-8', errors='ignore').splitlines(keepends=True)
    except OSError:
        return

    modified_lines: list[str] = []
    found = False
    for line in lines:
        if 'Options.bezels.value=' in line:
            modified_lines.append(re.sub(r'Options\.bezels\.value=\d+', f'Options.bezels.value={thickness if enabled else 0}', line))
            found = True
        elif 'TestSurface = Video_CreateSurfaceFromFile' in line and not found:
            modified_lines.append(line)
            modified_lines.append(f'\tOptions.bezels.value={thickness if enabled else 0}\r\n')
            found = True
        else:
            modified_lines.append(line)

    try:
        file_path.write_text(''.join(modified_lines), encoding='utf-8')
    except OSError:
        pass


def _modify_lua_model2_option(file_path: Path, needle: str, enabled: bool) -> None:
    try:
        text = file_path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return

    replacements = {
        'widescreen': [('Screen.Stretch = false', 'Screen.Stretch = true')],
        'scanlines': [('Screen.Scanlines = false', 'Screen.Scanlines = true')],
    }
    changed = False
    for off_text, on_text in replacements.get(needle, []):
        if off_text in text or on_text in text:
            text = text.replace(off_text, on_text if enabled else off_text)
            changed = True
    if changed:
        try:
            file_path.write_text(text, encoding='utf-8')
        except OSError:
            pass


def _ensure_model2_runtime_root(bin_path: Path) -> Path:
    source_root = bin_path.parent.parent
    source_emu = source_root / 'emulator'
    if not source_emu.exists():
        source_root = MODEL2_SOURCE_EMU.parent
        source_emu = MODEL2_SOURCE_EMU
    if not source_emu.exists():
        raise FileNotFoundError(MODEL2_SOURCE_EMU)

    _sync_tree(source_root, MODEL2_RUNTIME_ROOT)
    _sync_tree(source_emu / 'scripts', MODEL2_RUNTIME_EMU / 'scripts')
    _sync_tree(source_emu / 'CFG', MODEL2_RUNTIME_EMU / 'CFG')
    return MODEL2_RUNTIME_EMU


def _write_model2_config(ctx: LaunchContext, runtime_emu: Path) -> Path:
    conf = _load_effective_hippos_conf()
    config_path = runtime_emu / 'EMULATOR.INI'
    parser = _new_ini_parser()
    if config_path.exists():
        parser.read(config_path, encoding='utf-8')

    for section in ('Renderer', 'Input', 'RomDirs'):
        if not parser.has_section(section):
            parser.add_section(section)

    display_resolution = _display_resolution_from_conf(conf)
    if display_resolution is not None:
        parser.set('Renderer', 'FullScreenWidth', str(display_resolution[0]))
        parser.set('Renderer', 'FullScreenHeight', str(display_resolution[1]))
    else:
        parser.set('Renderer', 'FullScreenWidth', '0')
        parser.set('Renderer', 'FullScreenHeight', '0')
    parser.set('Renderer', 'FullMode', _conf_value(conf, 'model2_renderRes', '4'))
    parser.set('Renderer', 'AutoFull', '1')
    parser.set('Renderer', 'ForceSync', '1')
    parser.set('Renderer', 'FakeGouraud', _conf_value(conf, 'model2_fakeGouraud', '0'))
    parser.set('Renderer', 'Bilinear', _conf_value(conf, 'model2_bilinearFiltering', '1'))
    parser.set('Renderer', 'Trilinear', _conf_value(conf, 'model2_trilinearFiltering', '0'))
    parser.set('Renderer', 'FilterTilemaps', _conf_value(conf, 'model2_filterTilemaps', '0'))
    parser.set('Renderer', 'ForceManaged', _conf_value(conf, 'model2_forceManaged', '0'))
    parser.set('Renderer', 'AutoMip', _conf_value(conf, 'model2_enableMIP', '0'))
    parser.set('Renderer', 'MeshTransparency', _conf_value(conf, 'model2_meshTransparency', '0'))
    parser.set('Renderer', 'FSAA', _conf_value(conf, 'model2_fullscreenAA', '0'))
    parser.set('Input', 'UseRawInput', _conf_value(conf, 'model2_useRawInput', '0'))
    parser.set('Input', 'XInput', '1' if _conf_bool(conf, 'model2_xinput', False) else '0')
    parser.set('Input', 'EnableFF', '1' if _conf_bool(conf, 'model2_forceFeedback', False) else '0')

    if _conf_value(conf, 'model2_crossHairs', ''):
        parser.set('Renderer', 'DrawCross', _conf_value(conf, 'model2_crossHairs', '0'))
    elif ctx.lightgun:
        parser.set('Renderer', 'DrawCross', '1')
    else:
        parser.set('Renderer', 'DrawCross', '0')

    rom_dirs = [MODEL2_ROMS]
    if MODEL2_ROMS.exists():
        for candidate in MODEL2_ROMS.iterdir():
            if candidate.is_dir() and candidate.name != 'images':
                rom_dirs.append(candidate)
    for idx, rom_dir in enumerate(rom_dirs, start=1):
        parser.set('RomDirs', f'Dir{idx}', f'Z:{rom_dir}')

    with config_path.open('w', encoding='utf-8') as fh:
        parser.write(fh)

    lua_file = runtime_emu / 'scripts' / f'{ctx.rom.stem}.lua'
    if lua_file.exists():
        _modify_lua_model2_option(lua_file, 'widescreen', _conf_bool(conf, 'model2_ratio', False))
        _modify_lua_model2_option(lua_file, 'scanlines', _conf_bool(conf, 'model2_scanlines', False))

    known_gun_roms = {'bel', 'gunblade', 'hotd', 'rchase2', 'vcop', 'vcop2', 'vcopa'}
    if ctx.lightgun and ctx.rom.stem in known_gun_roms:
        thickness = _model2_border_thickness(display_resolution[0] if display_resolution is not None else 1280)
        _modify_lua_model2_sinden(lua_file, True, thickness)
    elif lua_file.exists():
        _modify_lua_model2_sinden(lua_file, False, '0')

    return config_path


def launch_model2emu(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('model2emu')
    if bin_path is None:
        return 1

    runtime_emu = _ensure_model2_runtime_root(bin_path)
    config_path = _write_model2_config(ctx, runtime_emu)

    conf = _load_effective_hippos_conf()
    cmd: list[str] = [str(bin_path), ctx.rom.stem]
    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    if _conf_value(conf, 'model2_Software', '0') == '1':
        env.update({
            '__GLX_VENDOR_LIBRARY_NAME': 'mesa',
            'MESA_LOADER_DRIVER_OVERRIDE': 'llvmpipe',
            'GALLIUM_DRIVER': 'llvmpipe',
        })

    result = _run_game_command(ctx, 'model2emu', cmd, env, cwd=runtime_emu)
    return result.returncode
