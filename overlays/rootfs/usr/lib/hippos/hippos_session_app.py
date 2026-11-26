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


def _loginctl(*args: str) -> str:
    return subprocess.run(['loginctl', *args, '--value'], capture_output=True, text=True).stdout.strip()


def session_type() -> str:
    display_session = _loginctl('show-user', SESSION_USER, '-p', 'Display')
    return _loginctl('show-session', display_session, '-p', 'Type') if display_session else ''


def published_env() -> dict[str, str]:
    shown = subprocess.run(['systemctl', '--user', f'--machine={SESSION_USER}@.host', 'show-environment'],
                           capture_output=True, text=True).stdout
    return dict(line.split('=', 1) for line in shown.splitlines() if '=' in line)


def session_env() -> dict[str, str]:
    user = pwd.getpwnam(SESSION_USER)
    runtime_dir = f'/run/user/{user.pw_uid}'
    env = {**os.environ,
           'HOME': user.pw_dir,
           'DISPLAY': os.environ.get('DISPLAY', ':0'),
           'XDG_RUNTIME_DIR': runtime_dir,
           'DBUS_SESSION_BUS_ADDRESS': f'unix:path={runtime_dir}/bus'}
    env.pop('WAYLAND_DISPLAY', None)
    if session_type() == 'wayland':
        wayland_display = os.environ.get('WAYLAND_DISPLAY') or published_env().get('WAYLAND_DISPLAY')
        if wayland_display:
            env['WAYLAND_DISPLAY'] = wayland_display
    return env


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
