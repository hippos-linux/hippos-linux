from __future__ import annotations

import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

CONTEXT_FILE        = Path('/run/hippos/hotkeys.context')
PID_FILE            = Path('/run/hippos/hotkeys.pid')
KEYBOARD_SHOWN_FILE = Path('/run/hippos/keyboard.shown')


def signal_daemon(sig: int = signal.SIGHUP) -> None:
    try:
        pid = int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        subprocess.run(
            ['sudo', '-n', 'kill', f'-{signal.Signals(sig).name}', str(pid)],
            capture_output=True,
        )


def new_context(name: str, keys: dict[str, Any], disable_common: bool = False) -> None:
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {'name': name, 'keys': keys}
    if disable_common:
        data['common_disabled'] = True
    tmp_path = CONTEXT_FILE.with_suffix('.tmp')
    tmp_path.write_text(json.dumps(data))
    os.replace(tmp_path, CONTEXT_FILE)
    KEYBOARD_SHOWN_FILE.unlink(missing_ok=True)
    signal_daemon()


def default_context() -> None:
    CONTEXT_FILE.unlink(missing_ok=True)
    KEYBOARD_SHOWN_FILE.unlink(missing_ok=True)
    signal_daemon()


def reload() -> None:
    signal_daemon()


def set_keyboard_shown(shown: bool) -> None:
    if shown:
        KEYBOARD_SHOWN_FILE.touch()
    else:
        KEYBOARD_SHOWN_FILE.unlink(missing_ok=True)
    signal_daemon(signal.SIGUSR1)
