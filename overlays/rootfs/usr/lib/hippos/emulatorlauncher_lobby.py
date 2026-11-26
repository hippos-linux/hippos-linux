from __future__ import annotations

import json
import threading
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

from emulatorlauncher_registry import Emulator
from emulatorlauncher_shared import LaunchContext, _conf_bool, _conf_value, _log

HIPPOS_LOBBY_URL = 'https://lobby.hippos-linux.org'
HEARTBEAT_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 5
UPNP_DISCOVER_MS = 500


@dataclass(frozen=True)
class LobbyGame:
    name: str
    crc: str


class LobbyError(Exception):
    pass


def lobby_game(ctx: LaunchContext) -> LobbyGame:
    name, crc = ctx.rom.stem, ''
    if ctx.gameinfoxml is not None and ctx.gameinfoxml.exists():
        try:
            game = ET.parse(ctx.gameinfoxml).getroot().find('game')
        except ET.ParseError as exc:
            _log.warning("lobby: could not parse %s: %s", ctx.gameinfoxml, exc)
            game = None
        if game is not None:
            name = game.findtext('name') or name
            crc = (game.findtext('crc32') or '').upper()
    return LobbyGame(name, crc)


def _lobby_request(method: str, url: str, body: Optional[dict] = None, token: str = '') -> Optional[dict]:
    import urllib.error
    import urllib.request
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content = response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise LobbyError(f'{method} {url}: {exc}') from exc
    return json.loads(content) if content else None


class UpnpPortMapping:
    PROTOCOLS = ('TCP', 'UDP')

    def __init__(self, port: int) -> None:
        self.port = port
        self._upnp = None

    def open(self) -> bool:
        try:
            import miniupnpc
            upnp = miniupnpc.UPnP()
            upnp.discoverdelay = UPNP_DISCOVER_MS
            if upnp.discover() == 0:
                _log.info("lobby: no UPnP router found")
                return False
            upnp.selectigd()
            for protocol in self.PROTOCOLS:
                upnp.addportmapping(self.port, protocol, upnp.lanaddr, self.port, 'HippOS netplay', '')
        except Exception as exc:
            _log.info("lobby: UPnP mapping of port %d failed: %s", self.port, exc)
            return False
        self._upnp = upnp
        _log.info("lobby: UPnP mapped port %d", self.port)
        return True

    def close(self) -> None:
        if self._upnp is None:
            return
        for protocol in self.PROTOCOLS:
            try:
                self._upnp.deleteportmapping(self.port, protocol)
            except Exception as exc:
                _log.info("lobby: UPnP unmapping %s %d failed: %s", protocol, self.port, exc)
        self._upnp = None


class HostedSession(threading.Thread):
    def __init__(self, port_mapping: Optional[UpnpPortMapping], lobby_url: str, room: Optional[dict]) -> None:
        super().__init__(name='lobby', daemon=True)
        self.port_mapping = port_mapping
        self.lobby_url = lobby_url
        self.room = room
        self.stopped = threading.Event()

    def run(self) -> None:
        upnp = self.port_mapping is not None and self.port_mapping.open()
        try:
            if self.room is None:
                self.stopped.wait()
            else:
                self._announce({**self.room, 'upnp': upnp})
        finally:
            if self.port_mapping is not None:
                self.port_mapping.close()

    def _announce(self, room: dict) -> None:
        try:
            created = _lobby_request('POST', f'{self.lobby_url}/rooms', room)
        except LobbyError as exc:
            _log.warning("lobby: could not announce the game: %s", exc)
            self.stopped.wait()
            return
        room_url = f'{self.lobby_url}/rooms/{created["id"]}'
        _log.info("lobby: announced room %s as %s:%d", created['id'], created.get('ip', '?'), room['port'])
        while not self.stopped.wait(HEARTBEAT_SECONDS):
            try:
                _lobby_request('PUT', room_url, token=created['token'])
            except LobbyError as exc:
                _log.warning("lobby: heartbeat failed: %s", exc)
        try:
            _lobby_request('DELETE', room_url, token=created['token'])
        except LobbyError as exc:
            _log.warning("lobby: could not remove room %s: %s", created['id'], exc)

    def stop(self) -> None:
        self.stopped.set()
        self.join()


def lobby_room(ctx: LaunchContext, port: int, nickname: str, has_password: bool = False) -> dict:
    game = lobby_game(ctx)
    return {
        'port': port,
        'emulator': ctx.emulator,
        'core_name': ctx.core,
        'game_name': game.name,
        'game_crc': game.crc,
        'username': nickname,
        'has_password': has_password,
    }


def _lobby_url(conf: dict[str, str]) -> str:
    return _conf_value(conf, 'global.netplay.hipposlobby', HIPPOS_LOBBY_URL).rstrip('/')


def _lists_hosted_games(conf: dict[str, str], ctx: LaunchContext) -> bool:
    return ctx.netplay.listed or _conf_bool(conf, 'global.netplay_public_announce')


@contextmanager
def launcher_hosted_session(conf: dict[str, str], ctx: LaunchContext, map_port: bool = True) -> Iterator[None]:
    announce = _lists_hosted_games(conf, ctx)
    if ctx.netplay.mode != 'host' or (not announce and not map_port):
        yield
        return
    port = int(ctx.netplay.port)
    session = HostedSession(
        UpnpPortMapping(port) if map_port else None,
        _lobby_url(conf),
        lobby_room(ctx, port, ctx.netplay.nickname) if announce else None,
    )
    session.start()
    try:
        yield
    finally:
        session.stop()


@contextmanager
def hosted_session(conf: dict[str, str], ctx: LaunchContext, emulator: Emulator) -> Iterator[None]:
    if ctx.netplay.mode != 'host' or emulator.netplay_announce != 'launcher':
        yield
        return
    with launcher_hosted_session(conf, ctx, emulator.netplay_upnp):
        yield


def parse_netplay_event(line: str) -> Optional[tuple[str, dict[str, str]]]:
    if not line.startswith('netplay '):
        return None
    event, *pairs = line[len('netplay '):].split()
    fields = {}
    for pair in pairs:
        key, separator, value = pair.partition('=')
        if separator:
            fields[key] = unquote(value)
    return event, fields


class NetplayEventAnnouncer:
    def __init__(self, conf: dict[str, str], ctx: LaunchContext) -> None:
        self.conf = conf
        self.ctx = ctx
        self.session: Optional[HostedSession] = None

    def __call__(self, line: str) -> None:
        parsed = parse_netplay_event(line.strip())
        if parsed is None:
            return
        event, fields = parsed
        if event == 'hosting':
            self._host(fields)
        elif event == 'stopped':
            self.close()

    def _host(self, fields: dict[str, str]) -> None:
        self.close()
        if not fields.get('port', '').isdigit():
            _log.warning("lobby: hosting event without a port: %s", fields)
            return
        port = int(fields['port'])
        nickname = fields.get('nick') or self.ctx.netplay.nickname
        room = None
        if _lists_hosted_games(self.conf, self.ctx):
            room = lobby_room(self.ctx, port, nickname, fields.get('password') == 'yes')
        self.session = HostedSession(UpnpPortMapping(port), _lobby_url(self.conf), room)
        self.session.start()

    def close(self) -> None:
        if self.session is not None:
            self.session.stop()
            self.session = None
