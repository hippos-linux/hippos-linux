from __future__ import annotations

import hashlib
import json
from pathlib import Path

from emulatorlauncher_shared import (
    ESBinding,
    LaunchContext,
    _build_game_env,
    _load_effective_hippos_conf,
    _load_es_input_configs,
    _pick_es_profile,
    _run_game_command,
    _require_emulator_bin,
)

from HipposPaths import BIOS, CONFIGS, SAVES
from emulatorlauncher_registry import Emulator, register

ARES_SAVES_ROOT = CONFIGS / 'ares' / 'saves'

_SYSTEM_MAP: dict[str, str] = {
    'nes':          'Famicom',
    'fds':          'Famicom Disk System',
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
    'pcenginecd':   'PC Engine CD',
    'neogeo':       'Neo Geo AES',
    'megacd32x':    'Mega CD 32X',
    'megald':       'Mega LD',
    'pceld':        'PC Engine LD',
    'myvision':     'MyVision',
    'zxspectrum128': 'ZX Spectrum 128',
}

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
    if binding.type == 'button':
        return f'{device_ident}/3/{binding.code}'
    if binding.type == 'hat':
        hat_x = binding.code * 2
        hat_y = binding.code * 2 + 1
        if binding.value == 1:
            return f'{device_ident}/1/{hat_y}/Lo'
        if binding.value == 4:
            return f'{device_ident}/1/{hat_y}/Hi'
        if binding.value == 8:
            return f'{device_ident}/1/{hat_x}/Lo'
        if binding.value == 2:
            return f'{device_ident}/1/{hat_x}/Hi'
    if binding.type == 'axis':
        qualifier = 'Lo' if binding.value < 0 else 'Hi'
        return f'{device_ident}/0/{binding.code}/{qualifier}'
    return ''

ARES_FIRMWARE: dict[str, tuple[tuple[str, str], ...]] = {
    'ColecoVision': (
        ('BIOS.World', '990bf1956f10207d8781b619eb74f89b00d921c8d45c95c334c16c8cceca09ad'),
    ),
    'Famicom Disk System': (
        ('BIOS.Japan', 'fdc1a76e654feea993fcb38366e05ee5f4eb641f86fe6bebaeefd412e112dd72'),
    ),
    'Game Boy Advance': (
        ('BIOS.World', 'fd2547724b505f487e6dcb29ec2ecff3af35a841a77ab2e85fd87350abd36570'),
    ),
    'Game Gear': (
        ('BIOS.World', '8c8a21335038285cfa03dc076100c1f0bfadf3e4ff70796f11f3dfaaab60eee2'),
    ),
    'Master System': (
        ('BIOS.US', '477617917a12a30f9f43844909dc2de6e6a617430f5c9a36306c86414a670d50'),
        ('BIOS.Japan', '67846e26764bd862f19179294347f7353a4166b62ac4198a5ec32933b7da486e'),
        ('BIOS.Europe', '477617917a12a30f9f43844909dc2de6e6a617430f5c9a36306c86414a670d50'),
    ),
    'Mega CD': (
        ('BIOS.US', 'fb477cdbf94c84424c2feca4fe40656d85393fe7b7b401911b45ad2eb991258c'),
        ('BIOS.Japan', '7133fc2dd2fe5b7d0acd53a5f10f3d00b5d31270239ad20d74ef32393e24af88'),
        ('BIOS.Europe', 'fe608a2a07676a23ab5fd5eee2f53c9e2526d69a28aa16ccd85c0ec42e6933cb'),
    ),
    'LaserActive (SEGA PAC)': (
        ('BIOS.US', 'e89b5a319f66406611ec82fe5c4aa6827c175a05135bd7bd177366cba0465021'),
        ('BIOS.Japan', 'dca942d977217f703d8d1c6eb1aeb6b32c78ecc421486bbb46c459d385161c94'),
    ),
    'MSX': (
        ('BIOS.Japan', '413a2b601a94b3792e054be2439cc77a1819cceadbfa9542f88d51c7480f2ef0'),
    ),
    'MSX2': (
        ('MAIN.Japan', '0c672d86ead61a97f49a583b88b7c1905da120645cd44f0c9f2baf4f4631e0b1'),
        ('SUB.Japan', '6c6f421a10c428d960b7ecc990f99af1c638147f747bddca7b0bf0e2ab738300'),
    ),
    'Neo Geo Pocket Color': (
        ('BIOS.World', '8fb845a2f71514cec20728e2f0fecfade69444f8d50898b92c2259f1ba63e10d'),
    ),
    'Neo Geo Pocket': (
        ('BIOS.World', '0293555b21c4fac516d25199df7809b26beeae150e1d4504a050db32264a6ad7'),
    ),
    'Nintendo 64DD': (
        ('BIOS.Japan', '806400ec0df94b0755de6c5b8249d6b6a9866124c5ddbdac198bde22499bfb8b'),
        ('BIOS.US', 'e9fec87a45fba02399e88064b9e2f8cf0f2106e351c58279a87f05da5bc984ad'),
        ('BIOS.DEV', '9c2962a8b994a29e4cd04b3a6e4ed730a751414655ab6a9799ebf5fc08b79d44'),
    ),
    'PC Engine CD': (
        ('System-Card-1.0.Japan', 'afe9f27f91ac918348555b86298b4f984643eafa2773196f2c5441ea84f0c3bb'),
        ('System-Card-3.0.Japan', 'e11527b3b96ce112a037138988ca72fd117a6b0779c2480d9e03eaebece3d9ce'),
        ('System-Card-3.0.US', 'cadac2725711b3c442bcf237b02f5a5210c96f17625c35fa58f009e0ed39e4db'),
    ),
    'LaserActive (NEC PAC)': (
        ('PAC-N10.US', '0e87a3385a27b3a4cac51934819b7eefa5b3d690768d2495633838488cd0e2e4'),
        ('PAC-N1.Japan', '459325690a458baebd77495c91e37c4dddfdd542ba13a821ce954e5bb245627f'),
        ('PCE-LP1.Japan', '3f43b3b577117d84002e99cb0baeb97b0d65b1d70b4adadc68817185c6a687f0'),
        ('System-Card-1.0.Japan', 'afe9f27f91ac918348555b86298b4f984643eafa2773196f2c5441ea84f0c3bb'),
    ),
    'PlayStation': (
        ('BIOS.US', '11052b6499e466bbf0a709b1f9cb6834a9418e66680387912451e971cf8a1fef'),
        ('BIOS.Japan', '9c0421858e217805f4abe18698afea8d5aa36ff0727eb8484944e00eb5e7eadb'),
        ('BIOS.Europe', '1faaa18fa820a0225e488d9f086296b8e6c46df739666093987ff7d8fd352c09'),
    ),
    'SuperGrafx CD': (
        ('Arcade-Card.Japan', 'e11527b3b96ce112a037138988ca72fd117a6b0779c2480d9e03eaebece3d9ce'),
    ),
}

ARES_FIRMWARE_HASH_CACHE = CONFIGS / 'ares' / 'firmware-hashes.json'
ARES_FIRMWARE_MAX_SIZE = 10 * 1024 * 1024

def _bios_file_hashes() -> dict[str, str]:
    try:
        cache = json.loads(ARES_FIRMWARE_HASH_CACHE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        cache = {}
    hashes: dict[str, str] = {}
    fresh: dict[str, list] = {}
    for path in BIOS.iterdir() if BIOS.is_dir() else ():
        if not path.is_file():
            continue
        stat = path.stat()
        if stat.st_size >= ARES_FIRMWARE_MAX_SIZE:
            continue
        cached = cache.get(str(path))
        if cached and cached[:2] == [stat.st_size, stat.st_mtime]:
            digest = cached[2]
        else:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        fresh[str(path)] = [stat.st_size, stat.st_mtime, digest]
        hashes[digest] = str(path)
    ARES_FIRMWARE_HASH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ARES_FIRMWARE_HASH_CACHE.write_text(json.dumps(fresh), encoding='utf-8')
    return hashes

def _ares_firmware_lines(ares_system: str | None) -> list[str]:
    firmware = ARES_FIRMWARE.get(ares_system or '')
    if not firmware:
        return []
    hashes = _bios_file_hashes()
    found = [(key, hashes[digest]) for key, digest in firmware if digest in hashes]
    if not found:
        return []
    base = ares_system.replace(' ', '').replace('(', '').replace(')', '')
    return [base, '  Firmware', *(f'    {key}: {location}' for key, location in found)]

def _ares_saves_lines(ares_system: str | None, system: str) -> list[str]:
    if not ares_system:
        return []
    link = ARES_SAVES_ROOT / ares_system
    target = SAVES / system
    if not (link.is_symlink() and link.readlink() == target):
        link.parent.mkdir(parents=True, exist_ok=True)
        link.unlink(missing_ok=True)
        link.symlink_to(target, target_is_directory=True)
    return ['Paths', f'  Saves: {ARES_SAVES_ROOT}/']

def _write_ares_settings(settings_file: Path, ctx: LaunchContext) -> None:
    profiles = _load_es_input_configs()
    guid_seen: dict[str, int] = {}

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
                lines.append(f'  {bml_key}: {assignment};;')
        pad_blocks.append('\n'.join(lines))

    bml_parts = [
        'Input',
        '  Driver',
        '    Name: SDL',
    ]
    bml_parts.extend(pad_blocks)
    bml_parts.extend(_ares_saves_lines(_SYSTEM_MAP.get(ctx.system), ctx.system))
    bml_parts.extend(_ares_firmware_lines(_SYSTEM_MAP.get(ctx.system)))

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text('\n'.join(bml_parts) + '\n', encoding='utf-8')

def launch_ares(ctx: LaunchContext) -> int:
    bin_path = _require_emulator_bin('ares')

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
    result = _run_game_command(ctx, cmd, env)
    return result.returncode

register(Emulator('ares', launch_ares))
