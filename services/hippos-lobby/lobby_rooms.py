from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus

from lobby_validation import LobbyError, text_field

ROOM_TTL_SECONDS = 90
MAX_ROOMS = 2000
MAX_ROOMS_PER_IP = 4
CREATES_PER_IP_PER_MINUTE = 10

_CRC = re.compile(r'^[0-9A-Fa-f]{8}$')
_CORE = re.compile(r'^[A-Za-z0-9_.+-]{1,64}$')


@dataclass
class Room:
    id: str
    token: str
    ip: str
    port: int
    emulator: str
    core_name: str
    game_name: str
    game_crc: str
    username: str
    has_password: bool
    upnp: bool
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def listing(self) -> dict:
        return {'fields': {
            'id': self.id,
            'username': self.username,
            'game_name': self.game_name,
            'game_crc': self.game_crc,
            'emulator': self.emulator,
            'core_name': self.core_name,
            'ip': self.ip,
            'port': self.port,
            'has_password': self.has_password,
            'has_spectate_password': False,
            'host_method': 0,
            'upnp': self.upnp,
            'frontend': 'HippOS',
            'created': _iso(self.created),
            'updated': _iso(self.updated),
        }}


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec='seconds')


def _parse_room(body: dict) -> dict:
    port = body.get('port')
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise LobbyError(HTTPStatus.BAD_REQUEST, 'invalid port')
    emulator = text_field(body, 'emulator')
    core_name = text_field(body, 'core_name')
    if not _CORE.match(emulator) or not _CORE.match(core_name):
        raise LobbyError(HTTPStatus.BAD_REQUEST, 'invalid emulator or core_name')
    game_crc = text_field(body, 'game_crc', required=False).upper()
    if game_crc and not _CRC.match(game_crc):
        raise LobbyError(HTTPStatus.BAD_REQUEST, 'invalid game_crc')
    return {
        'port': port,
        'emulator': emulator,
        'core_name': core_name,
        'game_name': text_field(body, 'game_name'),
        'game_crc': game_crc,
        'username': text_field(body, 'username'),
        'has_password': body.get('has_password') is True,
        'upnp': body.get('upnp') is True,
    }


class Rooms:
    def __init__(self, clock=time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._rooms: dict[str, Room] = {}
        self._creates: dict[str, list[float]] = {}

    def _expire(self, now: float) -> None:
        for room_id in [r.id for r in self._rooms.values() if now - r.updated > ROOM_TTL_SECONDS]:
            del self._rooms[room_id]
        for ip in list(self._creates):
            self._creates[ip] = [t for t in self._creates[ip] if now - t < 60]
            if not self._creates[ip]:
                del self._creates[ip]

    def create(self, ip: str, body: dict) -> Room:
        fields = _parse_room(body)
        now = self._clock()
        with self._lock:
            self._expire(now)
            if len(self._creates.get(ip, [])) >= CREATES_PER_IP_PER_MINUTE:
                raise LobbyError(HTTPStatus.TOO_MANY_REQUESTS, 'too many rooms created')
            if len(self._rooms) >= MAX_ROOMS or sum(r.ip == ip for r in self._rooms.values()) >= MAX_ROOMS_PER_IP:
                raise LobbyError(HTTPStatus.TOO_MANY_REQUESTS, 'too many open rooms')
            room = Room(id=secrets.token_hex(8), token=secrets.token_urlsafe(24), ip=ip,
                        created=now, updated=now, **fields)
            self._rooms[room.id] = room
            self._creates.setdefault(ip, []).append(now)
            return room

    def _owned(self, room_id: str, token: str) -> Room:
        room = self._rooms.get(room_id)
        if room is None:
            raise LobbyError(HTTPStatus.NOT_FOUND, 'no such room')
        if not secrets.compare_digest(room.token, token):
            raise LobbyError(HTTPStatus.FORBIDDEN, 'wrong token')
        return room

    def heartbeat(self, room_id: str, token: str) -> None:
        now = self._clock()
        with self._lock:
            self._expire(now)
            self._owned(room_id, token).updated = now

    def delete(self, room_id: str, token: str) -> None:
        with self._lock:
            self._owned(room_id, token)
            del self._rooms[room_id]

    def listing(self) -> list[dict]:
        with self._lock:
            self._expire(self._clock())
            return [r.listing() for r in sorted(self._rooms.values(), key=lambda r: r.created)]
