from __future__ import annotations

from emulatorlauncher_duckstation import DuckStationFamily, launch_family
from emulatorlauncher_registry import Emulator, register
from emulatorlauncher_shared import LaunchContext, _conf_value, _game_value, _load_hippos_conf

_DEFAULT_NETPLAY_PORT = '31200'


def _riverhorse_settings(settings, conf, ctx: LaunchContext) -> None:
    settings.set('GPU', 'UseHardwareThread', _game_value(conf, ctx, 'riverhorse_hardware_thread', 'false'))


def _riverhorse_netplay_args(ctx: LaunchContext) -> list[str]:
    port = ctx.netplay_port or _DEFAULT_NETPLAY_PORT
    nickname = _conf_value(_load_hippos_conf(), 'global.netplay.nickname', '')
    nickname_args = ['-netplaynick', nickname] if nickname else []
    if ctx.netplay_mode == 'host':
        return ['-netplayhost', port, *nickname_args]
    if ctx.netplay_mode in ('client', 'spectator') and ctx.netplay_ip:
        spectate_args = ['-netplayspectate'] if ctx.netplay_mode == 'spectator' else []
        return ['-netplayjoin', f'{ctx.netplay_ip}:{port}', *nickname_args, *spectate_args]
    return []


RIVERHORSE = DuckStationFamily('riverhorse', 'Riverhorse', ('riverhorse',), _riverhorse_settings,
                               _riverhorse_netplay_args, pad_order=(0, 2, 3, 4, 1, 5, 6, 7))

register(Emulator('riverhorse', lambda ctx: launch_family(RIVERHORSE, ctx)))
