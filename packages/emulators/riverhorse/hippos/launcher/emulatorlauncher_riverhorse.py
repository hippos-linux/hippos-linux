from __future__ import annotations

from HipposPaths import EMULATORS_ROOT
from emulatorlauncher_duckstation import DuckStationFamily, launch_family
from emulatorlauncher_lobby import NetplayEventAnnouncer, launcher_hosted_session
from emulatorlauncher_registry import Emulator, register
from emulatorlauncher_shared import LaunchContext, _conf_bool, _conf_value, _game_value, _load_hippos_conf, _log

_DEFAULT_NETPLAY_PORT = '31200'
_LAST_VERSION_WITHOUT_FRONTEND_NETPLAY_OPTIONS = (1, 2, 0)


def _riverhorse_settings(settings, conf, ctx: LaunchContext) -> None:
    settings.set('GPU', 'UseHardwareThread', _game_value(conf, ctx, 'riverhorse_hardware_thread', 'false'))


def _installed_version() -> tuple[int, ...]:
    try:
        text = (EMULATORS_ROOT / 'riverhorse' / 'version').read_text().strip().lstrip('v')
        return tuple(int(part) for part in text.split('.'))
    except (OSError, ValueError) as exc:
        _log.info("riverhorse: version unknown (%s)", exc)
        return ()


def _has_frontend_netplay_options() -> bool:
    return _installed_version() > _LAST_VERSION_WITHOUT_FRONTEND_NETPLAY_OPTIONS


def _riverhorse_netplay_args(ctx: LaunchContext) -> list[str]:
    conf = _load_hippos_conf()
    frontend_options = _has_frontend_netplay_options()
    events_args = ['-netplayevents'] if frontend_options else []
    port = ctx.netplay_port or _DEFAULT_NETPLAY_PORT
    nickname = _conf_value(conf, 'global.netplay.nickname', '')
    nickname_args = ['-netplaynick', nickname] if nickname else []
    if ctx.netplay_mode == 'host':
        public = frontend_options and _conf_bool(conf, 'global.netplay_public_announce')
        return ['-netplayhost', port, *(['-netplaypublic'] if public else []), *nickname_args, *events_args]
    if ctx.netplay_mode in ('client', 'spectator') and (ctx.netplay.session or ctx.netplay_ip):
        spectate_args = ['-netplayspectate'] if ctx.netplay_mode == 'spectator' else []
        target = ctx.netplay.session or f'{ctx.netplay_ip}:{port}'
        return ['-netplayjoin', target, *nickname_args, *spectate_args, *events_args]
    return events_args


RIVERHORSE = DuckStationFamily('riverhorse', 'Riverhorse', ('riverhorse',), _riverhorse_settings,
                               _riverhorse_netplay_args, pad_order=(0, 2, 3, 4, 1, 5, 6, 7))


def launch_riverhorse(ctx: LaunchContext) -> int:
    conf = _load_hippos_conf()
    if not _has_frontend_netplay_options():
        with launcher_hosted_session(conf, ctx):
            return launch_family(RIVERHORSE, ctx)
    announcer = NetplayEventAnnouncer(conf, ctx)
    try:
        return launch_family(RIVERHORSE, ctx, announcer)
    finally:
        announcer.close()


register(Emulator('riverhorse', launch_riverhorse, netplay_announce='emulator'))
