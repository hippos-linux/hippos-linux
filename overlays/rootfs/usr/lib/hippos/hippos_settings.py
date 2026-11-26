#!/usr/bin/env python3

from __future__ import annotations

import fcntl
import os
import sys
from contextlib import contextmanager
from pathlib import Path

USER_CONF      = Path('/userdata/system/hippos.conf')
HW_DEFAULTS    = Path('/run/hippos/hardware-defaults.conf')
DEFAULTS_CONF  = Path('/usr/share/hippos/hippos-defaults.conf')

_USAGE = 'Usage: hippos-settings get <key> | set <key> <value> [<key> <value> ...] | del <key> | list | dump | sync'

def _parse(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, _, v = line.partition('=')
                result[k.strip()] = v.strip()
    except OSError:
        pass
    return result

@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path.with_name(f'.{path.name}.lock'), os.O_RDONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)

def _write(path: Path, data: dict[str, str]) -> None:
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    tmp.write_text(''.join(f'{k}={v}\n' for k, v in sorted(data.items())), encoding='utf-8')
    if os.geteuid() == 0 and path.exists():
        owner = path.stat()
        os.chown(tmp, owner.st_uid, owner.st_gid)
    tmp.replace(path)

def cmd_get(key: str) -> int:
    for src in (USER_CONF, HW_DEFAULTS, DEFAULTS_CONF):
        data = _parse(src)
        if key in data:
            print(data[key])
            return 0
    return 1

def cmd_set(pairs: list[str]) -> int:
    with _locked(USER_CONF):
        data = _parse(USER_CONF)
        data.update(zip(pairs[::2], pairs[1::2]))
        _write(USER_CONF, data)
    return 0

def cmd_del(key: str) -> int:
    with _locked(USER_CONF):
        data = _parse(USER_CONF)
        if key in data:
            del data[key]
            _write(USER_CONF, data)
    return 0

def merged() -> dict[str, str]:
    return {**_parse(DEFAULTS_CONF), **_parse(HW_DEFAULTS), **_parse(USER_CONF)}

def cmd_list() -> int:
    for k, v in sorted(merged().items()):
        print(f'{k}={v}')
    return 0

def cmd_dump() -> int:
    for k, v in sorted(_parse(USER_CONF).items()):
        print(f'{k}={v}')
    return 0

def cmd_sync() -> int:
    defaults = {**_parse(DEFAULTS_CONF), **_parse(HW_DEFAULTS)}
    with _locked(USER_CONF):
        user = _parse(USER_CONF)
        missing = {k: v for k, v in defaults.items() if k not in user}
        if missing:
            user.update(missing)
            _write(USER_CONF, user)
    return 0

def main() -> int:
    args = sys.argv[1:]

    if not args:
        print(_USAGE, file=sys.stderr)
        return 1

    cmd, *rest = args
    if cmd == 'get' and len(rest) == 1:
        return cmd_get(rest[0])
    if cmd == 'set' and rest and len(rest) % 2 == 0:
        return cmd_set(rest)
    if cmd == 'del' and len(rest) == 1:
        return cmd_del(rest[0])
    if cmd == 'list' and not rest:
        return cmd_list()
    if cmd == 'dump' and not rest:
        return cmd_dump()
    if cmd == 'sync' and not rest:
        return cmd_sync()

    print(_USAGE, file=sys.stderr)
    return 1

if __name__ == '__main__':
    sys.exit(main())
