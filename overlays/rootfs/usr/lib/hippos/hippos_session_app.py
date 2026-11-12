from __future__ import annotations

import os
import pwd
import signal
import subprocess
from pathlib import Path

SESSION_USER = 'hippos'


def running_pid(pid_file: Path, script: Path) -> int | None:
    try:
        pid = int(pid_file.read_text())
        cmdline = Path(f'/proc/{pid}/cmdline').read_bytes()
    except (OSError, ValueError):
        return None
    return pid if pid != os.getpid() and str(script).encode() in cmdline else None


def session_env() -> dict[str, str]:
    runtime_dir = f'/run/user/{pwd.getpwnam(SESSION_USER).pw_uid}'
    return {**os.environ,
            'DISPLAY': os.environ.get('DISPLAY', ':0'),
            'XDG_RUNTIME_DIR': runtime_dir,
            'DBUS_SESSION_BUS_ADDRESS': f'unix:path={runtime_dir}/bus'}


def toggle(pid_file: Path, script: Path, start_args: list[str]) -> None:
    pid = running_pid(pid_file, script)
    if pid is not None:
        os.kill(pid, signal.SIGUSR1)
        return
    command = [str(script), *start_args]
    if os.geteuid() == 0:
        command = ['runuser', '-u', SESSION_USER, '--'] + command
    subprocess.Popen(command, env=session_env(), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def claim(pid_file: Path, script: Path) -> bool:
    if running_pid(pid_file, script) is not None:
        return False
    pid_file.write_text(str(os.getpid()))
    return True


def release(pid_file: Path) -> None:
    try:
        if int(pid_file.read_text()) == os.getpid():
            pid_file.unlink()
    except (OSError, ValueError):
        pass
