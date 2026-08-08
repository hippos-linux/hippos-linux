from __future__ import annotations

from pathlib import Path

from emulatorlauncher_shared import (
    ESBinding,
    LaunchContext,
    _build_game_env,
    _find_emulator_bin,
    _load_effective_hippos_conf,
    _load_es_input_configs,
    _pick_es_profile,
    _run_game_command,
)

from HipposPaths import CONFIGS, SAVES


_SYSTEM_MAP: dict[str, str] = {
    'nes':          'Famicom',
    'fds':          'Famicom',
    'snes':         'Super Famicom',
    'snes-msu1':    'Super Famicom',
    'sgb':          'Super Famicom',
    'gb':           'Game Boy',
    'gbc':          'Game Boy Color',
    'gba':          'Game Boy Advance',
    'n64':          'Nintendo 64',
    'mastersystem': 'Master System',
    'megadrive':    'Mega Drive',
    'sega32x':      'Mega 32X',
    'megacd':       'Mega CD',
    'gamegear':     'Game Gear',
    'sg1000':       'SG-1000',
    'sc3000':       'SC-3000',
    'pcengine':     'PC Engine',
    'supergrafx':   'SuperGrafx',
    'psx':          'PlayStation',
    'wswan':        'WonderSwan',
    'wswanc':       'WonderSwan Color',
    'ngp':          'Neo Geo Pocket',
    'ngpc':         'Neo Geo Pocket Color',
    'atari2600':    'Atari 2600',
    'colecovision': 'ColecoVision',
    'msx1':         'MSX',
    'msx2':         'MSX2',
    'saturn':       'Saturn',
    'n64dd':        'Nintendo 64DD',
    'pcenginecd':   'PC Engine',
    'neogeo':       'Neo Geo AES',
    'megacd32x':    'Mega CD 32X',
    'megald':       'Mega LD',
    'pceld':        'PC Engine LD',
    'myvision':     'MyVision',
    'zxspectrum128': 'ZX Spectrum 128',
}

# Maps ES input name → ares VirtualPad settings.bml key
# Key is the sanitised BML node name (spaces→dot, (→dot, )→removed)
_ES_TO_VIRTUALPAD: dict[str, str] = {
    'up':            'Pad.Up',
    'down':          'Pad.Down',
    'left':          'Pad.Left',
    'right':         'Pad.Right',
    'select':        'Select',
    'start':         'Start',
    'a':             'A..South',
    'b':             'B..East',
    'x':             'X..West',
    'y':             'Y..North',
    'pageup':        'L-Bumper',
    'pagedown':      'R-Bumper',
    'l2':            'L-Trigger',
    'r2':            'R-Trigger',
    'l3':            'L-Stick..Click',
    'r3':            'R-Stick..Click',
    'joystick1up':   'L-Up',
    'joystick1down': 'L-Down',
    'joystick1left': 'L-Left',
    'joystick1right':'L-Right',
    'joystick2up':   'R-Up',
    'joystick2down': 'R-Down',
    'joystick2left': 'R-Left',
    'joystick2right':'R-Right',
}


def _binding_to_ares(binding: ESBinding, device_ident: str) -> str:
    """Convert ESBinding to an ares input assignment string."""
    # Ares group IDs: 0=Axis, 1=Hat, 2=Trigger, 3=Button
    if binding.type == 'button':
        return f'{device_ident}/3/{binding.code}'
    if binding.type == 'hat':
        # Ares encodes each physical hat as two axis-like inputs:
        # hat_n * 2     = X (horizontal): Lo=left, Hi=right
        # hat_n * 2 + 1 = Y (vertical):   Lo=up,   Hi=down
        hat_x = binding.code * 2
        hat_y = binding.code * 2 + 1
        if binding.value == 1:   # up
            return f'{device_ident}/1/{hat_y}/Lo'
        if binding.value == 4:   # down
            return f'{device_ident}/1/{hat_y}/Hi'
        if binding.value == 8:   # left
            return f'{device_ident}/1/{hat_x}/Lo'
        if binding.value == 2:   # right
            return f'{device_ident}/1/{hat_x}/Hi'
    if binding.type == 'axis':
        qualifier = 'Lo' if binding.value < 0 else 'Hi'
        return f'{device_ident}/0/{binding.code}/{qualifier}'
    return ''


def _write_ares_settings(settings_file: Path, ctx: LaunchContext) -> None:
    profiles = _load_es_input_configs()
    guid_seen: dict[str, int] = {}

    # Build per-player VirtualPad BML blocks
    pad_blocks: list[str] = []
    for nplayer, ctrl in enumerate(ctx.controllers, start=1):
        profile = _pick_es_profile(profiles, ctrl)
        if profile is None:
            continue

        guid = profile.device_guid.lower().replace('-', '')
        slot = guid_seen.get(guid, 0)
        guid_seen[guid] = slot + 1
        device_ident = f'{guid}/{slot}'

        lines: list[str] = [f'VirtualPad{nplayer}']
        for es_name, bml_key in _ES_TO_VIRTUALPAD.items():
            binding = profile.inputs.get(es_name)
            if binding is None:
                continue
            assignment = _binding_to_ares(binding, device_ident)
            if assignment:
                # BindingLimit=3: write first binding, leave other 2 empty
                lines.append(f'  {bml_key}: {assignment};;')
        pad_blocks.append('\n'.join(lines))

    # Assemble settings.bml
    bml_parts = [
        'Input',
        '  Driver',
        '    Name: SDL',
    ]
    bml_parts.extend(pad_blocks)

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text('\n'.join(bml_parts) + '\n', encoding='utf-8')


def launch_ares(ctx: LaunchContext) -> int:
    bin_path = _find_emulator_bin('ares')
    if bin_path is None:
        return 1

    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)

    settings_file = CONFIGS / 'ares' / 'settings.bml'
    try:
        _write_ares_settings(settings_file, ctx)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("ares: could not write settings.bml: %s", exc)

    conf = _load_effective_hippos_conf()
    ares_system = _SYSTEM_MAP.get(ctx.system)

    cmd = [str(bin_path), '--fullscreen', '--no-file-prompt',
           '--settings-file', str(settings_file)]
    if ares_system:
        cmd += ['--system', ares_system]
    cmd.append(str(ctx.rom))

    env = _build_game_env(conf, ctx)
    result = _run_game_command(ctx, 'ares', cmd, env)
    return result.returncode
