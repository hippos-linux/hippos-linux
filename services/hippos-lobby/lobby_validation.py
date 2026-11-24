from __future__ import annotations

from http import HTTPStatus

MAX_TEXT = 128


class LobbyError(ValueError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def text_field(body: dict, key: str, required: bool = True, limit: int = MAX_TEXT) -> str:
    value = body.get(key, '')
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise LobbyError(HTTPStatus.BAD_REQUEST, f'invalid {key}')
    if any(ord(ch) < 32 for ch in value):
        raise LobbyError(HTTPStatus.BAD_REQUEST, f'invalid {key}')
    return value.strip()
