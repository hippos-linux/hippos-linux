from __future__ import annotations

import ipaddress
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Optional

from lobby_validation import LobbyError, text_field

GLOBAL_CHANNEL = 'global'
MAX_MESSAGE = 200
MAX_NICKNAME = 32
MESSAGES_PER_CHANNEL = 200
MESSAGE_TTL_SECONDS = 2 * 60 * 60
MIN_SECONDS_BETWEEN_MESSAGES = 1.5
MESSAGES_PER_IP_PER_MINUTE = 15

_CHANNEL = re.compile(r'^[a-z0-9_-]{1,32}$')


def channel_name(name: str) -> str:
    if not _CHANNEL.match(name):
        raise LobbyError(HTTPStatus.NOT_FOUND, 'no such channel')
    return name


class WatchedFile:
    def __init__(self, path: Optional[Path]) -> None:
        self.path = path
        self._mtime: Optional[float] = None
        self._lines: list[str] = []

    def lines(self) -> list[str]:
        if self.path is None:
            return []
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            self._mtime, self._lines = None, []
            return self._lines
        if mtime != self._mtime:
            text = self.path.read_text(encoding='utf-8')
            self._lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith('#')]
            self._mtime = mtime
        return self._lines


class Moderation:
    def __init__(self, ban_list: Optional[Path] = None, word_filter: Optional[Path] = None) -> None:
        self._bans = WatchedFile(ban_list)
        self._words = WatchedFile(word_filter)

    def is_banned(self, ip: str) -> bool:
        address = ipaddress.ip_address(ip)
        return any(address in ipaddress.ip_network(entry, strict=False) for entry in self._bans.lines())

    def check(self, ip: str) -> None:
        if self.is_banned(ip):
            raise LobbyError(HTTPStatus.FORBIDDEN, 'banned')

    def filter_text(self, text: str) -> str:
        for word in self._words.lines():
            text = re.sub(rf'\b{re.escape(word)}\b', lambda m: '*' * len(m.group(0)), text, flags=re.IGNORECASE)
        return text


@dataclass(frozen=True)
class Message:
    id: int
    time: float
    username: str
    text: str

    def listing(self) -> dict:
        return {'id': self.id, 'time': int(self.time), 'username': self.username, 'text': self.text}


class Chat:
    def __init__(self, moderation: Moderation, clock=time.time) -> None:
        self._moderation = moderation
        self._clock = clock
        self._lock = threading.Lock()
        self._channels: dict[str, deque[Message]] = {}
        self._sent: dict[str, deque[float]] = {}
        self._next_id = 1

    def _expire(self, now: float) -> None:
        for name in list(self._channels):
            messages = self._channels[name]
            while messages and now - messages[0].time > MESSAGE_TTL_SECONDS:
                messages.popleft()
            if not messages:
                del self._channels[name]
        for ip in list(self._sent):
            sent = self._sent[ip]
            while sent and now - sent[0] > 60:
                sent.popleft()
            if not sent:
                del self._sent[ip]

    def post(self, ip: str, channel: str, body: dict) -> Message:
        channel = channel_name(channel)
        self._moderation.check(ip)
        username = text_field(body, 'username', limit=MAX_NICKNAME)
        text = self._moderation.filter_text(text_field(body, 'text', limit=MAX_MESSAGE))
        now = self._clock()
        with self._lock:
            self._expire(now)
            sent = self._sent.setdefault(ip, deque())
            if sent and now - sent[-1] < MIN_SECONDS_BETWEEN_MESSAGES or len(sent) >= MESSAGES_PER_IP_PER_MINUTE:
                raise LobbyError(HTTPStatus.TOO_MANY_REQUESTS, 'slow down')
            sent.append(now)
            message = Message(self._next_id, now, username, text)
            self._next_id += 1
            self._channels.setdefault(channel, deque(maxlen=MESSAGES_PER_CHANNEL)).append(message)
            return message

    def messages(self, channel: str, after: int) -> list[dict]:
        channel = channel_name(channel)
        with self._lock:
            self._expire(self._clock())
            return [m.listing() for m in self._channels.get(channel, ()) if m.id > after]
