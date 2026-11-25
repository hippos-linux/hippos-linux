from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from emulatorlauncher_shared import (
    LaunchContext,
    _build_game_env,
    _conf_bool,
    _conf_value,
    _ensure_section,
    _find_emulator_bin,
    _game_value,
    _load_effective_hippos_conf,
    _load_hippos_conf,
    _log,
    _new_ini_parser,
    _run_game_command,
    generate_sdl_game_controller_config,
)
from emulatorlauncher_core import _gun_type
from HipposPaths import BIOS, CONFIGS, SAVES
from emulatorlauncher_registry import Emulator, register

_MULTITAP_PAD_PORT = {2: 1, 3: 1, 4: 1, 5: 2, 6: 2, 7: 2}
_MULTITAP_PORTS = {'Disabled': (), 'Port1Only': (1,), 'BothPorts': (1, 2)}

BIOS_NAMES = {
    'PathNTSCU': ('scph5501.bin', 'scph7001.bin', 'scph1001.bin', 'scph101.bin', 'psxonpsp660.bin'),
    'PathNTSCJ': ('scph5500.bin', 'scph7000.bin', 'scph1000.bin', 'psxonpsp660.bin'),
    'PathPAL':   ('scph5502.bin', 'scph5552.bin', 'scph7502.bin', 'scph1002.bin', 'psxonpsp660.bin'),
}


@dataclass(frozen=True)
class DuckStationFamily:
    name: str
    display_name: str
    binaries: tuple[str, ...]
    extra_settings: Callable
    extra_args: Callable[[LaunchContext], list[str]] = lambda ctx: []
    pad_order: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7)

    @property
    def option_prefix(self) -> str:
        return self.name

    @property
    def config_dir(self) -> Path:
        return CONFIGS / self.name

    @property
    def saves_dir(self) -> Path:
        return SAVES / self.name

    @property
    def settings_path(self) -> Path:
        return self.config_dir / 'settings.ini'


def _duckstation_settings(settings, conf, ctx: LaunchContext) -> None:
    settings.set('UI', 'UnofficialBuildWarningConfirmed', 'true')


DUCKSTATION = DuckStationFamily('duckstation', 'DuckStation', ('duckstation-qt', 'duckstation-nogui', 'duckstation'),
                                _duckstation_settings)


def _write_settings(family: DuckStationFamily, ctx: LaunchContext) -> None:
    conf = _load_effective_hippos_conf()
    family.config_dir.mkdir(parents=True, exist_ok=True)

    settings = _new_ini_parser()
    if family.settings_path.exists():
        settings.read(family.settings_path, encoding='utf-8')

    for section in ('Main', 'ControllerPorts', 'Console', 'BIOS', 'CPU', 'GPU', 'Display', 'Audio', 'GameList', 'Hotkeys', 'CDROM', 'UI', 'AutoUpdater', 'MemoryCards', 'Folders'):
        _ensure_section(settings, section)

    (family.saves_dir / 'memcards').mkdir(parents=True, exist_ok=True)
    settings.set('MemoryCards', 'Directory', str(family.saves_dir / 'memcards'))
    settings.set('Folders', 'SaveStates', str(family.saves_dir))

    settings.set('AutoUpdater', 'CheckAtStartup', 'false')
    family.extra_settings(settings, conf, ctx)

    settings.set('Main', 'SettingsVersion', '3')
    settings.set('Main', 'InhibitScreensaver', 'true')
    settings.set('Main', 'StartPaused', 'false')
    settings.set('Main', 'StartFullscreen', 'true')
    settings.set('Main', 'PauseOnFocusLoss', 'false')
    settings.set('Main', 'PauseOnMenu', 'true')
    settings.set('Main', 'ConfirmPowerOff', 'false')
    settings.set('Main', 'ApplyGameSettings', 'true')
    settings.set('Main', 'SetupWizardIncomplete', 'false')
    settings.set('Main', 'EmulationSpeed', _game_value(conf, ctx, f'{family.option_prefix}_clocking', '1'))
    settings.set('Main', 'SyncToHostRefreshRate', _game_value(conf, ctx, f'{family.option_prefix}_hrr', 'false'))
    settings.set('Main', 'Language', 'en')
    settings.set('Main', 'RewindEnable', 'true' if _conf_bool(conf, 'global.rewind', False) else 'false')

    settings.set('ControllerPorts', 'ControllerSettingsMigrated', 'true')
    settings.set('ControllerPorts', 'PointerXScale', '8')
    settings.set('ControllerPorts', 'PointerYScale', '8')
    settings.set('ControllerPorts', 'PointerXInvert', 'false')
    settings.set('ControllerPorts', 'PointerYInvert', 'false')

    for i in range(1, 9):
        pad = f'Pad{i}'
        if settings.has_section(pad):
            settings.remove_section(pad)
        settings.add_section(pad)
        settings.set(pad, 'Type', 'None')

    multitap = 'Disabled'
    for nplayer in range(1, len(ctx.controllers[:8]) + 1):
        if nplayer > 2:
            multitap = 'Port1Only'
        if nplayer > 4:
            multitap = 'BothPorts'
    settings.set('ControllerPorts', 'MultitapMode', multitap)

    player_pads = [pad for pad in family.pad_order
                   if _MULTITAP_PAD_PORT.get(pad) in (None, *_MULTITAP_PORTS[multitap])]
    for nplayer, ctrl in enumerate(ctx.controllers[:8], start=1):
        pad_num  = f'Pad{player_pads[nplayer - 1] + 1}'
        sdl_num  = f'SDL-{ctrl.index}'
        ctrl_key = f'{family.option_prefix}_Controller{nplayer}'
        ctrl_type = conf.get(ctrl_key, 'AnalogController')

        settings.set(pad_num, 'Type',        ctrl_type)
        settings.set(pad_num, 'Up',          f'{sdl_num}/DPadUp')
        settings.set(pad_num, 'Right',       f'{sdl_num}/DPadRight')
        settings.set(pad_num, 'Down',        f'{sdl_num}/DPadDown')
        settings.set(pad_num, 'Left',        f'{sdl_num}/DPadLeft')
        settings.set(pad_num, 'Triangle',    f'{sdl_num}/Y')
        settings.set(pad_num, 'Circle',      f'{sdl_num}/B')
        settings.set(pad_num, 'Cross',       f'{sdl_num}/A')
        settings.set(pad_num, 'Square',      f'{sdl_num}/X')
        settings.set(pad_num, 'Select',      f'{sdl_num}/Back')
        settings.set(pad_num, 'Start',       f'{sdl_num}/Start')
        settings.set(pad_num, 'L1',          f'{sdl_num}/LeftShoulder')
        settings.set(pad_num, 'R1',          f'{sdl_num}/RightShoulder')
        settings.set(pad_num, 'L2',          f'{sdl_num}/+LeftTrigger')
        settings.set(pad_num, 'R2',          f'{sdl_num}/+RightTrigger')
        settings.set(pad_num, 'L3',          f'{sdl_num}/LeftStick')
        settings.set(pad_num, 'R3',          f'{sdl_num}/RightStick')
        settings.set(pad_num, 'LLeft',       f'{sdl_num}/-LeftX')
        settings.set(pad_num, 'LRight',      f'{sdl_num}/+LeftX')
        settings.set(pad_num, 'LDown',       f'{sdl_num}/+LeftY')
        settings.set(pad_num, 'LUp',         f'{sdl_num}/-LeftY')
        settings.set(pad_num, 'RLeft',       f'{sdl_num}/-RightX')
        settings.set(pad_num, 'RRight',      f'{sdl_num}/+RightX')
        settings.set(pad_num, 'RDown',       f'{sdl_num}/+RightY')
        settings.set(pad_num, 'RUp',         f'{sdl_num}/-RightY')
        settings.set(pad_num, 'SmallMotor',  f'{sdl_num}/SmallMotor')
        settings.set(pad_num, 'LargeMotor',  f'{sdl_num}/LargeMotor')
        settings.set(pad_num, 'VibrationBias', '8')

        if ctrl_type == 'AnalogController':
            settings.set(pad_num, 'AnalogDPadInDigitalMode', _game_value(conf, ctx, f'{family.option_prefix}_digitalmode', 'true'))
            settings.set(pad_num, 'Analog', f'{sdl_num}/Guide')

        if ctrl_type == 'NeGcon':
            settings.set(pad_num, 'A',             f'{sdl_num}/B')
            settings.set(pad_num, 'B',             f'{sdl_num}/Y')
            settings.set(pad_num, 'I',             f'{sdl_num}/+RightTrigger')
            settings.set(pad_num, 'II',            f'{sdl_num}/+LeftTrigger')
            settings.set(pad_num, 'L',             f'{sdl_num}/LeftShoulder')
            settings.set(pad_num, 'R',             f'{sdl_num}/RightShoulder')
            settings.set(pad_num, 'SteeringLeft',  f'{sdl_num}/-LeftX')
            settings.set(pad_num, 'SteeringRight', f'{sdl_num}/+LeftX')

        if ctrl_type == 'PlayStationMouse':
            settings.set(pad_num, 'Right', f'{sdl_num}/B')
            settings.set(pad_num, 'Left',  f'{sdl_num}/A')

    settings.set('Console', 'Region', _game_value(conf, ctx, f'{family.option_prefix}_region', 'Auto'))
    settings.set('Console', 'EnableCheats', _game_value(conf, ctx, f'{family.option_prefix}_cheats', 'False'))
    settings.set('BIOS', 'SearchDirectory', str(BIOS))
    for key, names in BIOS_NAMES.items():
        found = next((name for name in names if (BIOS / name).is_file()), None)
        if found:
            settings.set('BIOS', key, found)
        elif settings.has_option('BIOS', key):
            settings.remove_option('BIOS', key)
    settings.set('BIOS', 'PatchFastBoot', _game_value(conf, ctx, f'{family.option_prefix}_PatchFastBoot', 'false'))
    settings.set('CPU', 'ExecutionMode', _game_value(conf, ctx, f'{family.option_prefix}_executionmode', 'Recompiler'))
    settings.set('GPU', 'Renderer', _conf_value(conf, f'{family.option_prefix}_gfxbackend', 'OpenGL'))
    settings.set('GPU', 'PerSampleShading', 'false')
    settings.set('GPU', 'Multisamples', '1')
    settings.set('GPU', 'ThreadedPresentation', _game_value(conf, ctx, f'{family.option_prefix}_threadedpresentation', 'false'))
    settings.set('GPU', 'ResolutionScale', _game_value(conf, ctx, f'{family.option_prefix}_resolution_scale', '1'))
    settings.set('GPU', 'WidescreenHack', _game_value(conf, ctx, f'{family.option_prefix}_widescreen_hack', 'false'))
    settings.set('GPU', 'ForceNTSCTimings', _game_value(conf, ctx, f'{family.option_prefix}_60hz', 'false'))
    settings.set('GPU', 'TextureFilter', _game_value(conf, ctx, f'{family.option_prefix}_texture_filtering', 'Nearest'))
    pgxp = _game_value(conf, ctx, f'{family.option_prefix}_pgxp', 'true')
    settings.set('GPU', 'PGXPEnable', pgxp)
    settings.set('GPU', 'PGXPCulling', pgxp)
    settings.set('GPU', 'PGXPTextureCorrection', pgxp)
    settings.set('GPU', 'PGXPPreserveProjFP', pgxp)
    settings.set('GPU', 'TrueColor', _game_value(conf, ctx, f'{family.option_prefix}_truecolour', 'false'))
    settings.set('GPU', 'ScaledDithering', _game_value(conf, ctx, f'{family.option_prefix}_dithering', 'true'))
    settings.set('GPU', 'DisableInterlacing', _game_value(conf, ctx, f'{family.option_prefix}_interlacing', 'false'))
    settings.set('Display', 'AspectRatio', _game_value(conf, ctx, f'{family.option_prefix}_ratio', 'Auto (Game Native)'))
    settings.set('Display', 'VSync', _game_value(conf, ctx, f'{family.option_prefix}_vsync', 'false'))
    settings.set('Display', 'CropMode', _game_value(conf, ctx, f'{family.option_prefix}_CropMode', 'Overscan'))
    settings.set('Display', 'DisplayAllFrames', _game_value(conf, ctx, f'{family.option_prefix}_ofp', 'false'))
    settings.set('Display', 'ShowOSDMessages', _game_value(conf, ctx, f'{family.option_prefix}_osd', 'false'))
    settings.set('Display', 'IntegerScaling', _game_value(conf, ctx, f'{family.option_prefix}_integer', 'false'))
    settings.set('Display', 'LinearFiltering', _game_value(conf, ctx, f'{family.option_prefix}_linear', 'false'))
    settings.set('Display', 'Stretch', _game_value(conf, ctx, f'{family.option_prefix}_stretch', 'false'))
    settings.set('Audio', 'StretchMode', _game_value(conf, ctx, f'{family.option_prefix}_audio_mode', 'TimeStretch'))
    if settings.has_option('GameList', 'RecursivePaths'):
        settings.remove_option('GameList', 'RecursivePaths')
    settings.set('Hotkeys', 'FastForward', 'Keyboard/Tab')
    settings.set('Hotkeys', 'Reset', 'Keyboard/F6')
    settings.set('Hotkeys', 'LoadSelectedSaveState', 'Keyboard/F1')
    settings.set('Hotkeys', 'SaveSelectedSaveState', 'Keyboard/F2')
    settings.set('Hotkeys', 'SelectPreviousSaveStateSlot', 'Keyboard/F3')
    settings.set('Hotkeys', 'SelectNextSaveStateSlot', 'Keyboard/F4')
    settings.set('Hotkeys', 'Screenshot', 'Keyboard/F10')
    settings.set('Hotkeys', 'Rewind', 'Keyboard/F5')
    settings.set('Hotkeys', 'OpenPauseMenu', 'Keyboard/F7')
    settings.set('Hotkeys', 'ChangeDisc', 'Keyboard/F8')
    if settings.has_option('Hotkeys', 'OpenQuickMenu'):
        settings.remove_option('Hotkeys', 'OpenQuickMenu')

    if ctx.lightgun:
        gun_type = _gun_type(ctx)
        gun_count = max(1, min(8, len(ctx.controllers) or 1))
        for nplayer in range(1, gun_count + 1):
            pad_num = f'Pad{nplayer}'
            gun_num = f'Pointer-{nplayer - 1}'
            if gun_type == 'justifier':
                settings.set(pad_num, 'Type', 'Justifier')
            else:
                settings.set(pad_num, 'Type', 'GunCon')
                pedal_keys = {1: 'c', 2: 'v', 3: 'b', 4: 'n'}
                pedal = conf.get(f'controllers.pedals{nplayer}', pedal_keys.get(nplayer, ''))
                if pedal:
                    settings.set(pad_num, 'A', f'{gun_num}/RightButton & Keyboard/{pedal.upper()}')
                else:
                    settings.set(pad_num, 'A', f'{gun_num}/RightButton')
            settings.set(pad_num, 'CrosshairScale', _game_value(conf, ctx, f'{family.option_prefix}_crosshair', '0'))
            settings.set(pad_num, 'CrosshairColor', '0000FF' if nplayer == 1 else 'FF0000')

    with family.settings_path.open('w', encoding='utf-8') as fh:
        settings.write(fh)

    _log.info("Wrote %s config: %s", family.display_name, family.settings_path)

def launch_family(family: DuckStationFamily, ctx: LaunchContext,
                  on_output_line: Optional[Callable[[str], None]] = None) -> int:
    bin_path = _find_emulator_bin(*family.binaries)
    if bin_path is None:
        _log.error("%s not found", family.display_name)
        return 1

    (SAVES / ctx.system).mkdir(parents=True, exist_ok=True)
    _write_settings(family, ctx)

    conf = _load_hippos_conf()
    db_path = family.config_dir / 'gamecontrollerdb.txt'
    db_path.write_text(generate_sdl_game_controller_config(ctx.controllers))

    if bin_path.name == 'duckstation-nogui':
        cmd = [str(bin_path), '-batch', '-fullscreen', *family.extra_args(ctx), '--', str(ctx.rom)]
    else:
        cmd = [str(bin_path), '-batch', '-nogui', *family.extra_args(ctx), '--', str(ctx.rom)]
    _log.info("Launching %s: %s", family.display_name, ' '.join(cmd))

    env = _build_game_env(conf, ctx)
    env['SDL_JOYSTICK_HIDAPI'] = '0'
    result = _run_game_command(ctx, cmd, env, on_output_line=on_output_line)
    return result.returncode


register(Emulator('duckstation', lambda ctx: launch_family(DUCKSTATION, ctx)))
