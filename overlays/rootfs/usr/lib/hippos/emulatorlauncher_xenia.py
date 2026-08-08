from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_bool,
    _conf_int,
    _conf_value,
    _find_emulator_bin,
    _load_effective_hippos_conf,
    _probe_vulkan_version,
    _read_toml,
    _run_game_command,
    _sync_tree,
    _write_toml,
    configure_emulator,
)

from HipposPaths import CACHE, HOME, SAVES, USERDATA


def _xenia_runtime_paths(core: str) -> tuple[Path, Path, Path]:
    runtime_dir = XENIA_CANARY_RUNTIME_DIR if core == 'xenia-canary' else XENIA_RUNTIME_DIR
    prefix_dir = XENIA_CANARY_PREFIX_DIR if core == 'xenia-canary' else XENIA_PREFIX_DIR
    bundle_dir = XENIA_CANARY_BUNDLE_DIR if core == 'xenia-canary' else XENIA_BUNDLE_DIR
    config_dir = runtime_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    prefix_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    XENIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    XENIA_SAVES_DIR.mkdir(parents=True, exist_ok=True)
    exe_name = 'xenia_canary.exe' if core == 'xenia-canary' else 'xenia.exe'
    exe_link = config_dir / exe_name
    exe_target = bundle_dir / exe_name
    if exe_link.exists() or exe_link.is_symlink():
        try:
            if exe_link.resolve() != exe_target.resolve():
                exe_link.unlink()
        except OSError:
            exe_link.unlink(missing_ok=True)
    if not exe_link.exists():
        exe_link.symlink_to(exe_target)
    patches_src = bundle_dir / 'patches'
    patches_dst = runtime_dir / 'patches'
    if patches_src.exists():
        _sync_tree(patches_src, patches_dst)
    portable_txt = config_dir / 'portable.txt'
    if not portable_txt.exists():
        portable_txt.touch()
    return runtime_dir, prefix_dir, config_dir


def _xenia_base_config(display_resolution: Optional[tuple[int, int]]) -> dict[str, object]:
    return {
        'CPU': {'break_on_unimplemented_instructions': False},
        'Content': {'license_mask': 1},
        'D3D12': {'d3d12_readback_resolve': False},
        'Display': {'fullscreen': True, 'internal_display_resolution': 8},
        'GPU': {
            'gpu': 'd3d12',
            'vsync': True,
            'framerate_limit': 0,
            'clear_memory_page_state': False,
            'render_target_path_d3d12': 'rtv',
            'query_occlusion_fake_sample_count': 1000,
            'texture_cache_memory_limit_hard': 768,
            'texture_cache_memory_limit_render_to_texture': 24,
            'texture_cache_memory_limit_soft': 384,
            'texture_cache_memory_limit_soft_lifetime': 30,
        },
        'General': {'discord': False, 'apply_patches': False},
        'HID': {'hid': 'sdl'},
        'Logging': {'log_level': 1},
        'Memory': {'protect_zero': False},
        'Storage': {
            'cache_root': str(XENIA_CACHE_DIR),
            'content_root': str(XENIA_SAVES_DIR),
            'mount_scratch': True,
            'storage_root': str(XENIA_RUNTIME_DIR),
            'mount_cache': True,
        },
        'UI': {'headless': False, 'show_achievement_notification': False},
        'Vulkan': {'vulkan_sparse_shared_memory': False},
        'XConfig': {'user_country': 103, 'user_language': 1},
    }


def _write_xenia_config(ctx: LaunchContext) -> tuple[Path, Path, Path]:
    conf = _load_effective_hippos_conf()
    core = ctx.core or ctx.emulator
    runtime_dir, prefix_dir, config_dir = _xenia_runtime_paths(core)
    toml_file = config_dir / ('xenia-canary.config.toml' if core == 'xenia-canary' else 'xenia.config.toml')

    config = _read_toml(toml_file) or _xenia_base_config(None)
    if not config:
        config = _xenia_base_config(None)

    config.setdefault('CPU', {})['break_on_unimplemented_instructions'] = False
    config.setdefault('Content', {})['license_mask'] = _conf_int(conf, 'xenia_license', 1)
    config.setdefault('D3D12', {})['d3d12_readback_resolve'] = _conf_bool(conf, 'xenia_readback_resolve', False)

    display = config.setdefault('Display', {})
    display['fullscreen'] = True
    if core == 'xenia-canary':
        display['internal_display_resolution'] = _conf_int(conf, 'xenia_resolution', 8)

    gpu = config.setdefault('GPU', {})
    api = _conf_value(conf, 'xenia_api', 'D3D12')
    if api.upper() == 'D3D12':
        vulkan_version = _probe_vulkan_version()
        if vulkan_version is not None and vulkan_version < (1, 3):
            api = 'Vulkan'
    gpu['gpu'] = api.lower()
    gpu['vsync'] = _conf_bool(conf, 'xenia_vsync', True)
    gpu['framerate_limit'] = _conf_int(conf, 'xenia_vsync_fps', 0)
    gpu['clear_memory_page_state'] = _conf_bool(conf, 'xenia_page_state', False)
    gpu['render_target_path_d3d12'] = _conf_value(conf, 'xenia_target_path', 'rtv')
    gpu['query_occlusion_fake_sample_count'] = _conf_int(conf, 'xenia_query_occlusion', 1000)
    gpu['texture_cache_memory_limit_hard'] = _conf_int(conf, 'xenia_limit_hard', 768)
    gpu['texture_cache_memory_limit_render_to_texture'] = _conf_int(conf, 'xenia_limit_render_to_texture', 24)
    gpu['texture_cache_memory_limit_soft'] = _conf_int(conf, 'xenia_limit_soft', 384)
    gpu['texture_cache_memory_limit_soft_lifetime'] = _conf_int(conf, 'xenia_limit_soft_lifetime', 30)

    general = config.setdefault('General', {})
    general['discord'] = False
    general['apply_patches'] = _conf_bool(conf, 'xenia_patches', False)

    config.setdefault('HID', {})['hid'] = 'sdl'
    config.setdefault('Logging', {})['log_level'] = 1
    config.setdefault('Memory', {})['protect_zero'] = False

    storage = config.setdefault('Storage', {})
    storage['cache_root'] = str(XENIA_CACHE_DIR)
    storage['content_root'] = str(XENIA_SAVES_DIR)
    storage['mount_scratch'] = True
    storage['storage_root'] = str(config_dir)
    storage['mount_cache'] = _conf_bool(conf, 'xenia_cache', True)

    ui = config.setdefault('UI', {})
    ui['headless'] = _conf_bool(conf, 'xenia_headless', False)
    ui['show_achievement_notification'] = _conf_bool(conf, 'xenia_achievement', False)

    vulkan_cfg = config.setdefault('Vulkan', {})
    vulkan_cfg['vulkan_sparse_shared_memory'] = False
    xcfg = config.setdefault('XConfig', {})
    xcfg['user_country'] = _conf_int(conf, 'xenia_country', 103)
    xcfg['user_language'] = _conf_int(conf, 'xenia_language', 1)

    _write_toml(toml_file, config)

    if core == 'xenia-canary' and _conf_bool(conf, 'xenia_patches', False):
        patches_dir = runtime_dir / 'patches'
        if patches_dir.exists():
            rom_name = re.sub(r'\[.*?\]', '', ctx.rom.stem)
            rom_name = re.sub(r'\(.*?\)', '', rom_name)
            matching_files = [path for path in patches_dir.glob(f'*{rom_name}*.patch.toml') if re.search(rom_name, path.name, re.IGNORECASE)]
            for file_path in matching_files:
                try:
                    text = file_path.read_text(encoding='utf-8')
                    text = re.sub(r'(?m)^(\s*is_enabled\s*=\s*)false\s*$', r'\1true', text)
                    file_path.write_text(text, encoding='utf-8')
                except Exception:
                    pass

    return runtime_dir, prefix_dir, config_dir


def launch_xenia(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin(ctx.emulator)
    if bin_path is None:
        return 1

    rom = ctx.rom
    if rom.suffix == '.xbox360':
        try:
            first_line = rom.read_text(encoding='utf-8').splitlines()[0].strip().lstrip('/')
            candidate = rom.parent / first_line
            if candidate.exists():
                rom = candidate
        except Exception:
            pass

    runtime_dir, prefix_dir, config_dir = _write_xenia_config(ctx)
    toml_file = config_dir / ('xenia-canary.config.toml' if ctx.core == 'xenia-canary' else 'xenia.config.toml')

    conf = _load_effective_hippos_conf()
    cmd = [str(bin_path)]
    if not configure_emulator(rom):
        cmd.append(f'z:{rom}')

    env = _build_game_env(conf, ctx)
    env['HOME'] = str(HOME)
    env['XENIA_HOME'] = str(runtime_dir)
    env['XENIA_PREFIX'] = str(prefix_dir)
    env['WINEPREFIX'] = str(prefix_dir)
    env['WINEARCH'] = 'win64'
    env['WINEDEBUG'] = '-all'
    env['VKD3D_SHADER_CACHE_PATH'] = str(XENIA_CACHE_DIR)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    env['LD_LIBRARY_PATH'] = f'/usr/lib:{env.get("LD_LIBRARY_PATH", "")}'
    env['LIBGL_DRIVERS_PATH'] = '/usr/lib/dri'
    env['XENIA_EXE'] = str(config_dir / ('xenia_canary.exe' if ctx.core == 'xenia-canary' else 'xenia.exe'))

    if Path('/var/tmp/hippos-nvidia.prime').exists():
        env.pop('__NV_PRIME_RENDER_OFFLOAD', None)
        env.pop('__VK_LAYER_NV_optimus', None)
        env.pop('__GLX_VENDOR_LIBRARY_NAME', None)
        env['VK_ICD_FILENAMES'] = '/usr/share/vulkan/icd.d/nvidia_icd.x86_64.json'
        env['VK_LAYER_PATH'] = '/usr/share/vulkan/explicit_layer.d'

    result = _run_game_command(ctx, ctx.emulator, cmd, env, cwd=config_dir)
    return result.returncode


XENIA_RUNTIME_DIR = USERDATA / 'emulators' / 'xenia' / 'current'
XENIA_CANARY_RUNTIME_DIR = USERDATA / 'emulators' / 'xenia-canary' / 'current'
XENIA_PREFIX_DIR = USERDATA / 'wine-bottles' / 'xenia' / 'current'
XENIA_CANARY_PREFIX_DIR = USERDATA / 'wine-bottles' / 'xenia-canary' / 'current'
XENIA_BUNDLE_DIR = Path('/opt/emulators/xenia/emulator')
XENIA_CANARY_BUNDLE_DIR = Path('/opt/emulators/xenia-canary/emulator')
XENIA_CACHE_DIR = CACHE / 'xenia'
XENIA_SAVES_DIR = SAVES / 'xbox360'
