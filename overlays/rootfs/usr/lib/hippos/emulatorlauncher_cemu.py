from __future__ import annotations

import xml.etree.ElementTree as ET

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_value,
    _find_emulator_bin,
    _load_hippos_conf,
    _log,
    _run_game_command,
)

from HipposPaths import SAVES, USERDATA


CEMU_CONFIG_DIR          = USERDATA / '.config' / 'cemu'
CEMU_SETTINGS_XML        = CEMU_CONFIG_DIR / 'settings.xml'
CEMU_CONTROLLER_PROFILES = CEMU_CONFIG_DIR / 'controllerProfiles'


_CEMU_GAMEPAD_BUTTONS = {
    "1": "1", "2": "0", "3": "3", "4": "2",
    "5": "9", "6": "10", "7": "42", "8": "43",
    "9": "6", "10": "4", "11": "11", "12": "12",
    "13": "13", "14": "14", "15": "7", "16": "8",
    "17": "45", "18": "39", "19": "44", "20": "38",
    "21": "47", "22": "41", "23": "46", "24": "40",
    "25": "7",
}
_CEMU_PRO_BUTTONS = {
    "1": "1", "2": "0", "3": "3", "4": "2",
    "5": "9", "6": "10", "7": "42", "8": "43",
    "9": "6", "10": "4",
    "12": "11", "13": "12", "14": "13", "15": "14",
    "16": "7", "17": "8",
    "18": "45", "19": "39", "20": "44", "21": "38",
    "22": "47", "23": "41", "24": "46", "25": "40",
}


def _write_cemu_config(conf: dict[str, str]) -> None:
    """Write Cemu settings.xml from hippos.conf values using xml.etree.ElementTree."""
    CEMU_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (SAVES / 'wiiu').mkdir(parents=True, exist_ok=True)

    def _get_or_create(parent: ET.Element, tag: str) -> ET.Element:
        el = parent.find(tag)
        if el is None:
            el = ET.SubElement(parent, tag)
        return el

    def _set_text(parent: ET.Element, tag: str, text: str) -> None:
        el = _get_or_create(parent, tag)
        el.text = text

    if CEMU_SETTINGS_XML.exists():
        try:
            tree = ET.parse(str(CEMU_SETTINGS_XML))
            root = tree.getroot()
        except Exception:
            root = ET.Element('content')
    else:
        root = ET.Element('content')

    # Root-level settings
    _set_text(root, 'mlc_path',           str(SAVES / 'wiiu'))
    _set_text(root, 'check_update',       'false')
    _set_text(root, 'gp_download',        'true')
    _set_text(root, 'logflag',            '0')
    _set_text(root, 'advanced_ppc_logging', 'false')
    _set_text(root, 'use_discord_presence', 'false')
    _set_text(root, 'fullscreen_menubar', 'false')
    _set_text(root, 'vk_warning',         'false')
    _set_text(root, 'fullscreen',         'true')

    # Language
    lang_val = _conf_value(conf, 'global.cemu_console_language', 'ui')
    if lang_val == 'ui':
        import os as _os
        lang = _os.environ.get('LANG', 'en_US')[:5]
    else:
        lang = lang_val
    lang_map = {'ja_JP': 0, 'en_US': 1, 'fr_FR': 2, 'de_DE': 3, 'it_IT': 4,
                'es_ES': 5, 'zh_CN': 6, 'ko_KR': 7, 'nl_NL': 8, 'pt_PT': 9,
                'ru_RU': 10, 'zh_TW': 11}
    _set_text(root, 'console_language', str(lang_map.get(lang, 1)))

    # Graphic section
    graphic = _get_or_create(root, 'Graphic')
    api_val = _conf_value(conf, 'global.cemu_gfxbackend', '1')
    _set_text(graphic, 'api',           api_val)
    async_val = _conf_value(conf, 'global.cemu_async', 'True')
    _set_text(graphic, 'AsyncCompile', 'true' if async_val.lower() in ('true', '1', 'on') else 'false')
    _set_text(graphic, 'VSync',        _conf_value(conf, 'global.cemu_vsync', '0'))
    _set_text(graphic, 'UpscaleFilter', _conf_value(conf, 'global.cemu_upscale', '2'))
    _set_text(graphic, 'DownscaleFilter', _conf_value(conf, 'global.cemu_downscale', '0'))
    _set_text(graphic, 'FullscreenScaling', _conf_value(conf, 'global.cemu_aspect', '0'))

    # Audio section
    audio = _get_or_create(root, 'Audio')
    _set_text(audio, 'api',         '3')  # cubeb
    _set_text(audio, 'TVChannels',  _conf_value(conf, 'global.cemu_audio_channels', '1'))
    _set_text(audio, 'TVVolume',    '100')

    # GamePaths
    game_paths = _get_or_create(root, 'GamePaths')
    _set_text(game_paths, 'Entry', str(USERDATA / 'roms' / 'wiiu'))

    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')
    with CEMU_SETTINGS_XML.open('wb') as fh:
        tree.write(fh, encoding='utf-8', xml_declaration=True)
    _log.info("Wrote Cemu config: %s", CEMU_SETTINGS_XML)


def _write_cemu_controller_profiles(ctx: LaunchContext) -> None:
    """Write per-controller XML profiles for Cemu."""
    CEMU_CONTROLLER_PROFILES.mkdir(parents=True, exist_ok=True)

    # Remove stale profiles
    for old in CEMU_CONTROLLER_PROFILES.glob('controller*.xml'):
        old.unlink(missing_ok=True)

    for idx, ctrl in enumerate(ctx.controllers[:5]):
        controller_type = 'Wii U GamePad' if idx == 0 else 'Wii U Pro Controller'
        btn_map = _CEMU_GAMEPAD_BUTTONS if idx == 0 else _CEMU_PRO_BUTTONS

        root = ET.Element('emulatedController')
        ET.SubElement(root, 'type').text = controller_type
        ET.SubElement(root, 'api').text = 'SDLController'
        ET.SubElement(root, 'controllerIndex').text = str(ctrl.index)
        ET.SubElement(root, 'rumble').text = 'false'
        ET.SubElement(root, 'deadzone').text = '0.25'
        ET.SubElement(root, 'range').text = '1'

        mappings = ET.SubElement(root, 'mappings')
        for mapping_id, btn_id in btn_map.items():
            entry = ET.SubElement(mappings, 'entry')
            ET.SubElement(entry, 'mapping').text = mapping_id
            ET.SubElement(entry, 'button').text = btn_id

        tree = ET.ElementTree(root)
        ET.indent(tree, space='  ')
        profile_path = CEMU_CONTROLLER_PROFILES / f'controller{idx}.xml'
        with profile_path.open('wb') as fh:
            tree.write(fh, encoding='utf-8', xml_declaration=True)

    _log.info("Wrote %d Cemu controller profiles", len(ctx.controllers[:5]))


def launch_cemu(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('cemu')
    if bin_path is None:
        _log.error("cemu not found")
        return 1
    (SAVES / 'wiiu').mkdir(parents=True, exist_ok=True)
    conf = _load_hippos_conf()
    _write_cemu_config(conf)
    _write_cemu_controller_profiles(ctx)
    cmd = [str(bin_path), '-f', '-g', str(ctx.rom), '--force-no-menubar']
    env = _build_game_env(conf, ctx)
    env['XDG_CONFIG_HOME'] = str(USERDATA / '.config')
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    result = _run_game_command(ctx, 'cemu', cmd, env)
    return result.returncode
