from __future__ import annotations

import codecs
import csv
import logging
import os
from pathlib import Path
from xml.dom import minidom

from emulatorlauncher_impl import (
    ESBinding,
    ESControllerProfile,
    LaunchContext,
    _load_es_input_configs,
    _pick_es_profile,
)

_log = logging.getLogger(__name__)

HIPPOS_MAME_DATA = Path('/usr/share/hippos/configgen/data/mame')

_SPECIAL_CONTROL_LIST = [
    'cdimono1', 'apfm1000', 'astrocde', 'adam', 'arcadia', 'gamecom', 'tutor',
    'crvision', 'bbcb', 'bbcm', 'bbcm512', 'bbcmc', 'xegs', 'socrates',
    'vgmplay', 'pdp1', 'vc4000', 'fmtmarty', 'gp32', 'apple2p', 'apple2e', 'apple2ee',
]


def get_mame_alt_layout(conf: dict[str, str], rom_path: Path) -> str:
    controller_type = conf.get('altlayout', 'auto')
    if controller_type in ('default', 'neomini', 'neocd', 'twinstick', 'qbert'):
        return controller_type

    rom_name = rom_path.stem

    def _load_set(fname: str) -> set[str]:
        f = HIPPOS_MAME_DATA / fname
        return set(f.read_text().split()) if f.exists() else set()

    capcom_list    = _load_set('mameCapcom.txt')
    mk_list        = _load_set('mameMKombat.txt')
    ki_list        = _load_set('mameKInstinct.txt')
    neogeo_list    = _load_set('mameNeogeo.txt')
    twinstick_list = _load_set('mameTwinstick.txt')
    qbert_list     = _load_set('mameRotatedstick.txt')

    if rom_name in capcom_list:
        if controller_type in ('auto', 'snes'):
            return 'sfsnes'
        if controller_type == 'megadrive':
            return 'megadrive'
        if controller_type == 'fightstick':
            return 'sfstick'
    elif rom_name in mk_list:
        if controller_type in ('auto', 'snes'):
            return 'mksnes'
        if controller_type == 'megadrive':
            return 'mkmegadrive'
        if controller_type == 'fightstick':
            return 'mkstick'
    elif rom_name in ki_list:
        if controller_type in ('auto', 'snes'):
            return 'kisnes'
        if controller_type == 'megadrive':
            return 'megadrive'
        if controller_type == 'fightstick':
            return 'sfstick'
    elif rom_name in neogeo_list:
        return 'neomini'
    elif rom_name in twinstick_list:
        return 'twinstick'
    elif rom_name in qbert_list:
        return 'qbert'
    else:
        if controller_type == 'fightstick':
            return 'fightstick'
        if controller_type == 'megadrive':
            return 'mddefault'

    return 'default'


def generate_mame_pads_config(cfg_dir: Path, ctx: LaunchContext, conf: dict[str, str]) -> None:
    cfg_dir.mkdir(parents=True, exist_ok=True)

    alt_layout = get_mame_alt_layout(conf, ctx.rom)
    sys_name   = ctx.rom.stem
    use_guns   = ctx.lightgun
    use_wheels = ctx.wheel
    custom_cfg = conf.get('mame_custom_cfg') == 'true'

    profiles = _load_es_input_configs()
    players: list[tuple] = []
    for ctrl in ctx.controllers:
        profile = _pick_es_profile(profiles, ctrl)
        if profile is not None:
            players.append((ctrl, profile))

    config = minidom.Document()
    config_file = cfg_dir / 'default.cfg'
    if config_file.exists():
        try:
            config = minidom.parse(str(config_file))
        except Exception:
            pass
    overwrite_mame = not (config_file.exists() and custom_cfg)

    control_file = HIPPOS_MAME_DATA / 'mameControls.csv'
    control_dict: dict[str, dict[str, str]] = {}
    if control_file.exists():
        with control_file.open('r') as f:
            for row in csv.reader(f):
                if row[0] not in control_dict:
                    control_dict[row[0]] = {}
                control_dict[row[0]][row[1]] = row[2]

    mappings: dict[str, str] = dict(control_dict.get('default', {}))
    gun_mappings: dict[str, str] = dict(control_dict.get('gunbuttons', {})) if use_guns else {}
    mouse_mappings: dict[str, str] = {}

    if alt_layout in control_dict:
        mappings.update(control_dict[alt_layout])

    xml_mameconfig = _get_root(config, 'mameconfig')
    xml_mameconfig.setAttribute('version', '10')
    xml_system = _get_section(config, xml_mameconfig, 'system')
    xml_system.setAttribute('name', 'default')

    _remove_section(config, xml_system, 'crosshairs')
    xml_crosshairs = config.createElement('crosshairs')
    crosshair_mode = conf.get('mame_crosshair', '')
    for p in range(4):
        xml_crosshair = config.createElement('crosshair')
        xml_crosshair.setAttribute('player', str(p))
        if crosshair_mode == 'enabled':
            xml_crosshair.setAttribute('mode', '1')
        elif crosshair_mode == 'onmove':
            continue
        else:
            xml_crosshair.setAttribute('mode', '0')
        xml_crosshairs.appendChild(xml_crosshair)
    xml_system.appendChild(xml_crosshairs)

    _remove_section(config, xml_system, 'input')
    xml_input = config.createElement('input')
    xml_system.appendChild(xml_input)

    mess_control_dict: dict = {}
    config_alt: minidom.Document | None = None
    xml_input_alt: minidom.Element | None = None
    config_file_alt: Path | None = None
    overwrite_system = True

    if sys_name in ('bbcb', 'bbcm', 'bbcm512', 'bbcmc'):
        use_controls = 'bbc'
    elif sys_name in ('apple2p', 'apple2e', 'apple2ee'):
        use_controls = 'apple2'
    else:
        use_controls = sys_name

    if sys_name in _SPECIAL_CONTROL_LIST:
        mess_file = HIPPOS_MAME_DATA / 'messControls.csv'
        if mess_file.exists():
            with mess_file.open('r') as f:
                for row in csv.reader(f, delimiter=';'):
                    if row[0] not in mess_control_dict:
                        mess_control_dict[row[0]] = {}
                    mess_control_dict[row[0]][row[1]] = {}
                    entry = mess_control_dict[row[0]][row[1]]
                    entry['type']   = row[2]
                    entry['player'] = int(row[3])
                    entry['tag']    = row[4]
                    entry['key']    = row[5]
                    if entry['type'] in ('special', 'main'):
                        entry['mapping']    = row[6]
                        entry['useMapping'] = row[7]
                        entry['reversed']   = row[8]
                        entry['mask']       = row[9]
                        entry['default']    = row[10]
                    elif entry['type'] == 'analog':
                        entry['incMapping']  = row[6]
                        entry['decMapping']  = row[7]
                        entry['useMapping1'] = row[8]
                        entry['useMapping2'] = row[9]
                        entry['reversed']    = row[10]
                        entry['mask']        = row[11]
                        entry['default']     = row[12]
                        entry['delta']       = row[13]
                        entry['axis']        = row[14]
                    if entry['type'] == 'combo':
                        entry['kbMapping']  = row[6]
                        entry['mapping']    = row[7]
                        entry['useMapping'] = row[8]
                        entry['reversed']   = row[9]
                        entry['mask']       = row[10]
                        entry['default']    = row[11]
                    entry['reversed'] = entry['reversed'] != 'False'

        config_alt = minidom.Document()
        config_file_alt = cfg_dir / f'{sys_name}.cfg'
        if config_file_alt.exists():
            try:
                config_alt = minidom.parse(str(config_file_alt))
            except Exception:
                pass
        if config_file_alt.exists() and custom_cfg:
            overwrite_system = False

        xml_mameconfig_alt = _get_root(config_alt, 'mameconfig')
        xml_mameconfig_alt.setAttribute('version', '10')
        xml_system_alt = _get_section(config_alt, xml_mameconfig_alt, 'system')
        xml_system_alt.setAttribute('name', sys_name)

        _remove_section(config_alt, xml_system_alt, 'input')
        xml_input_alt = config_alt.createElement('input')
        xml_system_alt.appendChild(xml_input_alt)

        if use_controls == 'cdimono1':
            _remove_section(config_alt, xml_system_alt, 'video')
            xml_video_alt = config_alt.createElement('video')
            xml_system_alt.appendChild(xml_video_alt)
            xml_screencfg = config_alt.createElement('target')
            xml_screencfg.setAttribute('index', '0')
            xml_screencfg.setAttribute('view', 'Main Screen Standard (4:3)')
            xml_video_alt.appendChild(xml_screencfg)

        if use_controls == 'bbc':
            xml_kbenable = config_alt.createElement('keyboard')
            xml_kbenable.setAttribute('tag', ':')
            xml_kbenable.setAttribute('enabled', '1')
            xml_input_alt.appendChild(xml_kbenable)

    for nplayer, (ctrl, profile) in enumerate(players, start=1):
        mappings_use = dict(mappings)
        if 'joystick1up' not in profile.inputs:
            mappings_use['JOYSTICK_UP']    = 'up'
            mappings_use['JOYSTICK_DOWN']  = 'down'
            mappings_use['JOYSTICK_LEFT']  = 'left'
            mappings_use['JOYSTICK_RIGHT'] = 'right'

        is_wheel = getattr(ctrl, 'is_wheel', False) and use_wheels
        if is_wheel:
            for k in list(mappings_use):
                if mappings_use[k] in ('l2', 'r2', 'joystick1left'):
                    del mappings_use[k]
            mappings_use['PEDAL']  = 'r2'
            mappings_use['PEDAL2'] = 'l2'
            mappings_use['PADDLE'] = 'joystick1left'

        _add_common_player_ports(config, xml_input, nplayer)

        pedal_keys = {1: 'c', 2: 'v', 3: 'b', 4: 'n'}
        pedal_key: str | None = conf.get(f'controllers.pedals{nplayer}') or pedal_keys.get(nplayer)

        for mapping, key in mappings_use.items():
            binding = profile.inputs.get(key)
            if binding is not None:
                if mapping in ('START', 'COIN'):
                    xml_input.appendChild(_gen_special_port_player(
                        profile, config, 'standard', nplayer, ctrl.index,
                        mapping, key, binding, False, '', '',
                        gun_mappings, mouse_mappings, False, pedal_key))
                else:
                    xml_input.appendChild(_gen_port(
                        profile, config, nplayer, ctrl.index, mapping, key, binding,
                        False, alt_layout, gun_mappings, is_wheel, mouse_mappings, False, pedal_key))
            else:
                rev_key = _reverse_mapping(key)
                if rev_key is not None:
                    rev_binding = profile.inputs.get(rev_key)
                    if rev_binding is not None:
                        xml_input.appendChild(_gen_port(
                            profile, config, nplayer, ctrl.index, mapping, key, rev_binding,
                            True, alt_layout, gun_mappings, is_wheel, mouse_mappings, False, pedal_key))

        if nplayer == 1:
            has_stick = 'joystick1up' in profile.inputs
            up_key   = mappings_use.get('JOYSTICK_UP', 'joystick1up')
            down_key = mappings_use.get('JOYSTICK_DOWN', 'joystick1down')
            left_key = mappings_use.get('JOYSTICK_LEFT', 'joystick1left')
            right_key = mappings_use.get('JOYSTICK_RIGHT', 'joystick1right')
            up_b   = profile.inputs.get(up_key)
            down_b = profile.inputs.get(down_key)
            left_b = profile.inputs.get(left_key)
            right_b = profile.inputs.get(right_key)
            if up_b and down_b and left_b and right_b:
                if has_stick:
                    xml_input.appendChild(_gen_combo_port(profile, config, 'standard', ctrl.index, 'UI_DOWN',  'DOWN',  down_key,  up_b,    False, '', ''))
                    xml_input.appendChild(_gen_combo_port(profile, config, 'standard', ctrl.index, 'UI_LEFT',  'LEFT',  left_key,  left_b,  False, '', ''))
                    xml_input.appendChild(_gen_combo_port(profile, config, 'standard', ctrl.index, 'UI_UP',    'UP',    up_key,    up_b,    False, '', ''))
                    xml_input.appendChild(_gen_combo_port(profile, config, 'standard', ctrl.index, 'UI_RIGHT', 'RIGHT', right_key, left_b,  False, '', ''))
                else:
                    xml_input.appendChild(_gen_combo_port(profile, config, 'standard', ctrl.index, 'UI_DOWN',  'DOWN',  down_key,  down_b,  False, '', ''))
                    xml_input.appendChild(_gen_combo_port(profile, config, 'standard', ctrl.index, 'UI_LEFT',  'LEFT',  left_key,  left_b,  False, '', ''))
                    xml_input.appendChild(_gen_combo_port(profile, config, 'standard', ctrl.index, 'UI_UP',    'UP',    up_key,    up_b,    False, '', ''))
                    xml_input.appendChild(_gen_combo_port(profile, config, 'standard', ctrl.index, 'UI_RIGHT', 'RIGHT', right_key, right_b, False, '', ''))
            b_binding = profile.inputs.get('b')
            if b_binding is not None:
                xml_input.appendChild(_gen_combo_port(profile, config, 'standard', ctrl.index, 'UI_SELECT', 'ENTER', 'b', b_binding, False, '', ''))

        if use_controls in mess_control_dict and config_alt is not None:
            for _ctrl_def, this_ctrl in mess_control_dict[use_controls].items():
                if nplayer != this_ctrl['player'] or xml_input_alt is None:
                    continue
                ctype = this_ctrl['type']
                if ctype in ('special', 'main'):
                    use_key = mappings_use.get(this_ctrl['useMapping'], '')
                    b1 = profile.inputs.get(use_key)
                    if b1 is None:
                        continue
                    target = xml_input_alt if ctype == 'special' else xml_input
                    target.appendChild(_gen_special_port(
                        profile, config_alt, this_ctrl['tag'], nplayer, ctrl.index,
                        this_ctrl['key'], this_ctrl['mapping'], b1,
                        this_ctrl['reversed'], this_ctrl['mask'], this_ctrl['default'], pedal_key))
                elif ctype == 'analog':
                    inc_es  = mappings_use.get(this_ctrl['incMapping'], '')
                    dec_es  = mappings_use.get(this_ctrl['decMapping'], '')
                    use_es1 = mappings_use.get(this_ctrl['useMapping1'], '')
                    use_es2 = mappings_use.get(this_ctrl['useMapping2'], '')
                    b_inc  = profile.inputs.get(use_es1)
                    b_dec  = profile.inputs.get(use_es2)
                    if b_inc is None or b_dec is None:
                        continue
                    xml_input_alt.appendChild(_gen_analog_port(
                        profile, config_alt, this_ctrl['tag'], nplayer, ctrl.index,
                        this_ctrl['key'], inc_es, dec_es, b_inc, b_dec,
                        this_ctrl['reversed'], this_ctrl['mask'], this_ctrl['default'],
                        this_ctrl['delta'], this_ctrl['axis']))
                elif ctype == 'combo':
                    use_key = mappings_use.get(this_ctrl['useMapping'], '')
                    b1 = profile.inputs.get(use_key)
                    if b1 is None:
                        continue
                    xml_input_alt.appendChild(_gen_combo_port(
                        profile, config_alt, this_ctrl['tag'], ctrl.index,
                        this_ctrl['key'], this_ctrl['kbMapping'], this_ctrl['mapping'], b1,
                        this_ctrl['reversed'], this_ctrl['mask'], this_ctrl['default']))

    if overwrite_mame:
        _log.debug("Saving %s", config_file)
        with codecs.open(str(config_file), 'w', 'utf-8') as f:
            dom_str = os.linesep.join(s for s in config.toprettyxml().splitlines() if s.strip())
            f.write(dom_str)

    if sys_name in _SPECIAL_CONTROL_LIST and overwrite_system and config_alt is not None and config_file_alt is not None:
        _log.debug("Saving %s", config_file_alt)
        with codecs.open(str(config_file_alt), 'w', 'utf-8') as f:
            dom_str = os.linesep.join(s for s in config_alt.toprettyxml().splitlines() if s.strip())
            f.write(dom_str)


def _reverse_mapping(key: str) -> str | None:
    if key == 'joystick1down':  return 'joystick1up'
    if key == 'joystick1right': return 'joystick1left'
    if key == 'joystick2down':  return 'joystick2up'
    if key == 'joystick2right': return 'joystick2left'
    return None


def _input2definition(profile: ESControllerProfile, key: str, binding: ESBinding, joycode: int,
                      reversed: bool, alt_layout: str | None,
                      ignore_axis: bool = False, is_wheel: bool = False) -> str:
    mame_axis_names = {0: 'XAXIS', 1: 'YAXIS', 2: 'ZAXIS', 3: 'RXAXIS', 4: 'RYAXIS', 5: 'RZAXIS'}

    if is_wheel and key in ('joystick1left', 'l2', 'r2'):
        suffix = '_NEG' if key in ('l2', 'r2') else ''
        if binding.code in mame_axis_names:
            return f'JOYCODE_{joycode}_{mame_axis_names[binding.code]}{suffix}'

    if binding.type == 'button':
        return f'JOYCODE_{joycode}_BUTTON{binding.code + 1}'

    if binding.type == 'hat':
        hat_map = {'1': 'UP', '2': 'RIGHT', '4': 'DOWN', '8': 'LEFT'}
        direction = hat_map.get(str(binding.value), 'UP')
        return f'JOYCODE_{joycode}_HAT1{direction}'

    if binding.type == 'axis':
        def _dpad_code(direction: str) -> str:
            b = profile.inputs.get(direction)
            if b is None:
                return ''
            if b.type == 'button':
                return f'JOYCODE_{joycode}_BUTTON{b.code + 1}'
            if b.type == 'hat':
                hat_map = {'1': 'UP', '2': 'RIGHT', '4': 'DOWN', '8': 'LEFT'}
                return f'JOYCODE_{joycode}_HAT1{hat_map.get(str(b.value), "UP")}'
            return ''

        dpad = {d: _dpad_code(d) for d in ('up', 'down', 'left', 'right')}

        def _btn_code(name: str) -> str:
            b = profile.inputs.get(name)
            if b is not None and b.type == 'button':
                return f'JOYCODE_{joycode}_BUTTON{b.code + 1}'
            return ''

        btn_dirs = {d: _btn_code(d) for d in ('a', 'b', 'x', 'y')}

        if ignore_axis and all(dpad[d] for d in ('up', 'down', 'left', 'right')):
            if key in ('joystick1up', 'up'):    return dpad['up']
            if key in ('joystick1down', 'down'): return dpad['down']
            if key in ('joystick1left', 'left'): return dpad['left']
            if key in ('joystick1right', 'right'): return dpad['right']

        if alt_layout == 'qbert':
            if key in ('joystick1up', 'up'):
                return f'JOYCODE_{joycode}_YAXIS_UP_SWITCH JOYCODE_{joycode}_XAXIS_RIGHT_SWITCH OR {dpad["up"]} {dpad["right"]}'
            if key in ('joystick1down', 'down'):
                return f'JOYCODE_{joycode}_YAXIS_DOWN_SWITCH JOYCODE_{joycode}_XAXIS_LEFT_SWITCH OR {dpad["down"]} {dpad["left"]}'
            if key in ('joystick1left', 'left'):
                return f'JOYCODE_{joycode}_XAXIS_LEFT_SWITCH JOYCODE_{joycode}_YAXIS_UP_SWITCH OR {dpad["left"]} {dpad["up"]}'
            if key in ('joystick1right', 'right'):
                return f'JOYCODE_{joycode}_XAXIS_RIGHT_SWITCH JOYCODE_{joycode}_YAXIS_DOWN_SWITCH OR {dpad["right"]} {dpad["down"]}'
        else:
            if key in ('joystick1up', 'up'):    return f'JOYCODE_{joycode}_YAXIS_UP_SWITCH OR {dpad["up"]}'
            if key in ('joystick1down', 'down'): return f'JOYCODE_{joycode}_YAXIS_DOWN_SWITCH OR {dpad["down"]}'
            if key in ('joystick1left', 'left'): return f'JOYCODE_{joycode}_XAXIS_LEFT_SWITCH OR {dpad["left"]}'
            if key in ('joystick1right', 'right'): return f'JOYCODE_{joycode}_XAXIS_RIGHT_SWITCH OR {dpad["right"]}'

        if profile.inputs:
            if key == 'joystick2up':    return f'JOYCODE_{joycode}_RYAXIS_NEG_SWITCH OR {btn_dirs["x"]}'
            if key == 'joystick2down':  return f'JOYCODE_{joycode}_RYAXIS_POS_SWITCH OR {btn_dirs["b"]}'
            if key == 'joystick2left':  return f'JOYCODE_{joycode}_RXAXIS_NEG_SWITCH OR {btn_dirs["y"]}'
            if key == 'joystick2right': return f'JOYCODE_{joycode}_RXAXIS_POS_SWITCH OR {btn_dirs["a"]}'
            if binding.code in mame_axis_names:
                return f'JOYCODE_{joycode}_{mame_axis_names[binding.code]}_POS_SWITCH'

    return 'unknown'


def _gen_port(profile: ESControllerProfile, config: minidom.Document,
              nplayer: int, padindex: int, mapping: str, key: str, binding: ESBinding,
              reversed: bool, alt_layout: str | None, gun_mappings: dict[str, str],
              is_wheel: bool, mouse_mappings: dict[str, str], multi_mouse: bool,
              pedal_key: str | None) -> minidom.Element:
    xml_port = config.createElement('port')
    xml_port.setAttribute('type', f'P{nplayer}_{mapping}')
    xml_newseq = config.createElement('newseq')
    xml_newseq.setAttribute('type', 'standard')
    xml_port.appendChild(xml_newseq)
    keyval = _input2definition(profile, key, binding, padindex + 1, reversed, alt_layout, False, is_wheel)
    if mapping in gun_mappings:
        keyval += f' OR GUNCODE_{nplayer}_{gun_mappings[mapping]}'
        if gun_mappings[mapping] == 'BUTTON2' and pedal_key is not None:
            keyval += f' OR KEYCODE_{pedal_key.upper()}'
    if mapping in mouse_mappings:
        suffix = f'MOUSECODE_{nplayer}_{mouse_mappings[mapping]}' if multi_mouse else f'MOUSECODE_1_{mouse_mappings[mapping]}'
        keyval += f' OR {suffix}'
    xml_newseq.appendChild(config.createTextNode(keyval))
    return xml_port


def _gen_special_port_player(profile: ESControllerProfile, config: minidom.Document,
                              tag: str, nplayer: int, padindex: int,
                              mapping: str, key: str, binding: ESBinding,
                              reversed: bool, mask: str, default: str,
                              gun_mappings: dict[str, str], mouse_mappings: dict[str, str],
                              multi_mouse: bool, pedal_key: str | None) -> minidom.Element:
    xml_port = config.createElement('port')
    xml_port.setAttribute('tag', tag)
    xml_port.setAttribute('type', mapping + str(nplayer))
    xml_port.setAttribute('mask', mask)
    xml_port.setAttribute('defvalue', default)
    xml_newseq = config.createElement('newseq')
    xml_newseq.setAttribute('type', 'standard')
    xml_port.appendChild(xml_newseq)
    keyval = _input2definition(profile, key, binding, padindex + 1, reversed, None)
    if mapping == 'COIN' and nplayer <= 4:
        keyval += f' OR KEYCODE_{nplayer}_{nplayer + 4}'
    if mapping in gun_mappings:
        keyval += f' OR GUNCODE_{nplayer}_{gun_mappings[mapping]}'
        if gun_mappings[mapping] == 'BUTTON2' and pedal_key is not None:
            keyval += f' OR KEYCODE_{pedal_key.upper()}'
    if mapping in mouse_mappings:
        suffix = f'MOUSECODE_{nplayer}_{mouse_mappings[mapping]}' if multi_mouse else f'MOUSECODE_1_{mouse_mappings[mapping]}'
        keyval += f' OR {suffix}'
    xml_newseq.appendChild(config.createTextNode(keyval))
    return xml_port


def _gen_special_port(profile: ESControllerProfile, config: minidom.Document,
                      tag: str, nplayer: int, padindex: int,
                      mapping: str, key: str, binding: ESBinding,
                      reversed: bool, mask: str, default: str,
                      pedal_key: str | None) -> minidom.Element:
    xml_port = config.createElement('port')
    xml_port.setAttribute('tag', tag)
    xml_port.setAttribute('type', mapping)
    xml_port.setAttribute('mask', mask)
    xml_port.setAttribute('defvalue', default)
    xml_newseq = config.createElement('newseq')
    xml_newseq.setAttribute('type', 'standard')
    xml_port.appendChild(xml_newseq)
    xml_newseq.appendChild(config.createTextNode(
        _input2definition(profile, key, binding, padindex + 1, reversed, None)))
    return xml_port


def _gen_combo_port(profile: ESControllerProfile, config: minidom.Document,
                    tag: str, padindex: int, mapping: str, kbkey: str,
                    key: str, binding: ESBinding,
                    reversed: bool, mask: str, default: str) -> minidom.Element:
    xml_port = config.createElement('port')
    xml_port.setAttribute('tag', tag)
    xml_port.setAttribute('type', mapping)
    xml_port.setAttribute('mask', mask)
    xml_port.setAttribute('defvalue', default)
    xml_newseq = config.createElement('newseq')
    xml_newseq.setAttribute('type', 'standard')
    xml_port.appendChild(xml_newseq)
    xml_newseq.appendChild(config.createTextNode(
        f'KEYCODE_{kbkey} OR {_input2definition(profile, key, binding, padindex + 1, reversed, None)}'))
    return xml_port


def _gen_analog_port(profile: ESControllerProfile, config: minidom.Document,
                     tag: str, nplayer: int, padindex: int, mapping: str,
                     inckey: str, deckey: str,
                     inc_binding: ESBinding, dec_binding: ESBinding,
                     reversed: bool, mask: str, default: str,
                     delta: str, axis: str) -> minidom.Element:
    xml_port = config.createElement('port')
    xml_port.setAttribute('tag', tag)
    xml_port.setAttribute('type', mapping)
    xml_port.setAttribute('mask', mask)
    xml_port.setAttribute('defvalue', default)
    xml_port.setAttribute('keydelta', delta)
    xml_newseq_inc = config.createElement('newseq')
    xml_newseq_inc.setAttribute('type', 'increment')
    xml_port.appendChild(xml_newseq_inc)
    xml_newseq_inc.appendChild(config.createTextNode(
        _input2definition(profile, inckey, inc_binding, padindex + 1, reversed, None, True)))
    xml_newseq_dec = config.createElement('newseq')
    xml_newseq_dec.setAttribute('type', 'decrement')
    xml_port.appendChild(xml_newseq_dec)
    xml_newseq_dec.appendChild(config.createTextNode(
        _input2definition(profile, deckey, dec_binding, padindex + 1, reversed, None, True)))
    xml_newseq_std = config.createElement('newseq')
    xml_newseq_std.setAttribute('type', 'standard')
    xml_port.appendChild(xml_newseq_std)
    std_val = f'JOYCODE_{padindex + 1}_{axis}' if axis else 'NONE'
    xml_newseq_std.appendChild(config.createTextNode(std_val))
    return xml_port


def _add_common_player_ports(config: minidom.Document, xml_input: minidom.Element, nplayer: int) -> None:
    for axis, nanalog in (('X', 1), ('Y', 2)):
        xml_port = config.createElement('port')
        xml_port.setAttribute('tag', f':mainpcb:ANALOG{nanalog}')
        xml_port.setAttribute('type', f'P{nplayer}_AD_STICK_{axis}')
        xml_port.setAttribute('mask', '255')
        xml_port.setAttribute('defvalue', '128')
        xml_newseq = config.createElement('newseq')
        xml_newseq.setAttribute('type', 'standard')
        xml_port.appendChild(xml_newseq)
        xml_newseq.appendChild(config.createTextNode(f'GUNCODE_{nplayer}_{axis}AXIS'))
        xml_input.appendChild(xml_port)


def _get_root(config: minidom.Document, name: str) -> minidom.Element:
    nodes = config.getElementsByTagName(name)
    if nodes:
        return nodes[0]
    node = config.createElement(name)
    config.appendChild(node)
    return node


def _get_section(config: minidom.Document, xml_root: minidom.Element, name: str) -> minidom.Element:
    nodes = xml_root.getElementsByTagName(name)
    if nodes:
        return nodes[0]
    node = config.createElement(name)
    xml_root.appendChild(node)
    return node


def _remove_section(config: minidom.Document, xml_root: minidom.Element, name: str) -> None:
    nodes = xml_root.getElementsByTagName(name)
    for node in list(nodes):
        old = xml_root.removeChild(node)
        old.unlink()
