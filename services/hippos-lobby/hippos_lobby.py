#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

from lobby_chat import Chat, Moderation
from lobby_rooms import Rooms
from lobby_validation import LobbyError

MAX_BODY_BYTES = 4096

_ROOM_PATH = re.compile(r'/rooms/([0-9a-f]{16})')
_CHAT_PATH = re.compile(r'/chat/([^/]+)')


class LobbyHandler(BaseHTTPRequestHandler):
    rooms: Rooms
    chat: Chat
    moderation: Moderation
    trusted_proxies: frozenset[str] = frozenset()
    server_version = 'hippos-lobby'

    def _client_ip(self) -> str:
        peer = self.client_address[0]
        forwarded = self.headers.get('X-Forwarded-For', '')
        if peer in self.trusted_proxies and forwarded:
            peer = forwarded.split(',')[-1].strip()
        return str(ipaddress.ip_address(peer))

    def _send(self, status: HTTPStatus, payload: object = None) -> None:
        body = b'' if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_BODY_BYTES:
            raise LobbyError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, 'body too large')
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
        except ValueError:
            raise LobbyError(HTTPStatus.BAD_REQUEST, 'invalid json') from None
        if not isinstance(body, dict):
            raise LobbyError(HTTPStatus.BAD_REQUEST, 'invalid json')
        return body

    def _path(self) -> str:
        return urlsplit(self.path).path.rstrip('/') or '/'

    def _match(self, pattern: re.Pattern) -> str:
        match = pattern.fullmatch(self._path())
        if match is None:
            raise LobbyError(HTTPStatus.NOT_FOUND, 'not found')
        return match.group(1)

    def _token(self) -> str:
        return self.headers.get('Authorization', '').removeprefix('Bearer ').strip()

    def _handle(self, action: Callable[[], None]) -> None:
        try:
            action()
        except LobbyError as exc:
            self._send(exc.status, {'error': str(exc)})

    def do_GET(self) -> None:
        def get() -> None:
            if self._path() in ('/list', '/rooms'):
                self._send(HTTPStatus.OK, self.rooms.listing())
                return
            channel = self._match(_CHAT_PATH)
            after = parse_qs(urlsplit(self.path).query).get('after', ['0'])[0]
            self._send(HTTPStatus.OK, {'messages': self.chat.messages(channel, int(after) if after.isdigit() else 0)})
        self._handle(get)

    def do_POST(self) -> None:
        def post() -> None:
            ip = self._client_ip()
            if self._path() == '/rooms':
                self.moderation.check(ip)
                room = self.rooms.create(ip, self._body())
                self._send(HTTPStatus.CREATED, {'id': room.id, 'token': room.token, 'ip': room.ip})
                return
            message = self.chat.post(ip, self._match(_CHAT_PATH), self._body())
            self._send(HTTPStatus.CREATED, message.listing())
        self._handle(post)

    def do_PUT(self) -> None:
        def heartbeat() -> None:
            self.rooms.heartbeat(self._match(_ROOM_PATH), self._token())
            self._send(HTTPStatus.NO_CONTENT)
        self._handle(heartbeat)

    def do_DELETE(self) -> None:
        def delete() -> None:
            self.rooms.delete(self._match(_ROOM_PATH), self._token())
            self._send(HTTPStatus.NO_CONTENT)
        self._handle(delete)

    def log_message(self, format: str, *args) -> None:
        pass


def make_server(host: str, port: int, trusted_proxies: frozenset[str] = frozenset(),
                ban_list: Optional[Path] = None, word_filter: Optional[Path] = None) -> ThreadingHTTPServer:
    moderation = Moderation(ban_list, word_filter)
    handler = type('Handler', (LobbyHandler,), {
        'rooms': Rooms(),
        'chat': Chat(moderation),
        'moderation': moderation,
        'trusted_proxies': trusted_proxies,
    })
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description='HippOS netplay lobby')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8655)
    parser.add_argument('--trusted-proxy', action='append', default=[],
                        help='address whose X-Forwarded-For is trusted (the reverse proxy)')
    parser.add_argument('--ban-list', type=Path,
                        help='file of banned IP addresses or CIDR ranges, one per line; edits apply without a restart')
    parser.add_argument('--word-filter', type=Path,
                        help='file of words to mask in chat, one per line; edits apply without a restart')
    args = parser.parse_args()
    make_server(args.host, args.port, frozenset(args.trusted_proxy), args.ban_list, args.word_filter).serve_forever()


if __name__ == '__main__':
    main()
