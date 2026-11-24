from __future__ import annotations

import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
from http import HTTPStatus

from lobby_validation import LobbyError, text_field

ROOM_TTL_SECONDS = 90
CHALLENGER_TTL_SECONDS = 20
MAX_ROOMS = 2000
MAX_ROOMS_PER_IP = 4
CREATES_PER_IP_PER_MINUTE = 10

ROOM_MODES = ('listen', 'challenge')
PENDING = 'pending'
ACCEPTED = 'accepted'
DECLINED = 'declined'

_CRC = re.compile(r'^[0-9A-Fa-f]{8}$')
_CORE = re.compile(r'^[A-Za-z0-9_.+-]{1,64}$')


@dataclass
class Challenger:
    username: str
    ip: str
    token: str
    seen: float
    state: str = PENDING

    def for_host(self) -> dict:
        return {'username': self.username, 'ip': self.ip, 'state': self.state}


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
    mode: str = 'listen'
    challenger: Optional[Challenger] = None
    declined: set[str] = field(default_factory=set)
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
            'mode': self.mode,
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
    mode = body.get('mode', 'listen')
    if mode not in ROOM_MODES:
        raise LobbyError(HTTPStatus.BAD_REQUEST, 'invalid mode')
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
        'mode': mode,
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
        for room in self._rooms.values():
            if room.challenger and room.challenger.state == PENDING and now - room.challenger.seen > CHALLENGER_TTL_SECONDS:
                room.challenger = None
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

    def _room(self, room_id: str) -> Room:
        room = self._rooms.get(room_id)
        if room is None:
            raise LobbyError(HTTPStatus.NOT_FOUND, 'no such room')
        return room

    def status(self, room_id: str, token: str) -> dict:
        with self._lock:
            self._expire(self._clock())
            challenger = self._owned(room_id, token).challenger
            return {'challenger': challenger.for_host() if challenger else None}

    def challenge(self, room_id: str, ip: str, body: dict) -> dict:
        username = text_field(body, 'username')
        now = self._clock()
        with self._lock:
            self._expire(now)
            room = self._room(room_id)
            if room.mode != 'challenge':
                raise LobbyError(HTTPStatus.BAD_REQUEST, 'room does not take challenges')
            if room.challenger is not None:
                raise LobbyError(HTTPStatus.CONFLICT, 'room already taken')
            room.challenger = Challenger(username=username, ip=ip, token=secrets.token_urlsafe(24), seen=now)
            return {'token': room.challenger.token}

    def _own_challenge(self, room: Room, token: str) -> Optional[Challenger]:
        challenger = room.challenger
        if challenger and secrets.compare_digest(challenger.token, token):
            return challenger
        return None

    def challenge_state(self, room_id: str, token: str) -> dict:
        now = self._clock()
        with self._lock:
            self._expire(now)
            room = self._room(room_id)
            challenger = self._own_challenge(room, token)
            if challenger is None:
                if token in room.declined:
                    return {'state': DECLINED}
                raise LobbyError(HTTPStatus.NOT_FOUND, 'no such challenge')
            challenger.seen = now
            if challenger.state == ACCEPTED:
                return {'state': ACCEPTED, 'ip': room.ip, 'port': room.port}
            return {'state': challenger.state}

    def cancel_challenge(self, room_id: str, token: str) -> None:
        with self._lock:
            room = self._room(room_id)
            challenger = self._own_challenge(room, token)
            if challenger is None or challenger.state != PENDING:
                raise LobbyError(HTTPStatus.NOT_FOUND, 'no such challenge')
            room.challenger = None

    def answer(self, room_id: str, token: str, body: dict) -> None:
        accept = body.get('accept')
        if not isinstance(accept, bool):
            raise LobbyError(HTTPStatus.BAD_REQUEST, 'accept must be true or false')
        with self._lock:
            self._expire(self._clock())
            room = self._owned(room_id, token)
            if room.challenger is None or room.challenger.state != PENDING:
                raise LobbyError(HTTPStatus.CONFLICT, 'no challenger waiting')
            if accept:
                room.challenger.state = ACCEPTED
            else:
                room.declined.add(room.challenger.token)
                room.challenger = None

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
            open_rooms = [r for r in self._rooms.values() if r.challenger is None]
            return [r.listing() for r in sorted(open_rooms, key=lambda r: r.created)]
