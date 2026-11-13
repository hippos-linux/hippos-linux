from __future__ import annotations

import pwd
import shlex
import subprocess

SESSION_USER = 'hippos'
APP_NAME = 'HippOS Update'
ICON = 'system-software-update'
PROGRESS_STEP = 5


def _desktop_session_active() -> bool:
    session = subprocess.run(['hippos-settings', 'get', 'system.session'],
                             capture_output=True, text=True, check=False).stdout.strip()
    return session == 'desktop'


class DesktopNotifier:
    def __init__(self, enabled: bool | None = None) -> None:
        self.enabled = _desktop_session_active() if enabled is None else enabled
        self.notification_id = ''
        self.last_progress = -PROGRESS_STEP

    def _notify_send(self, summary: str, body: str, *options: str) -> list[str]:
        uid = pwd.getpwnam(SESSION_USER).pw_uid
        replace = ['--replace-id', self.notification_id] if self.notification_id else []
        return ['runuser', '-u', SESSION_USER, '--', 'env',
                f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus',
                'notify-send', '--app-name', APP_NAME, '--icon', ICON, '--print-id', *replace, *options,
                summary, body]

    def show(self, summary: str, body: str = '', progress: int | None = None) -> None:
        if not self.enabled:
            return
        hint = ['--hint', f'int:value:{progress}'] if progress is not None else []
        result = subprocess.run(self._notify_send(summary, body, *hint), capture_output=True, text=True, check=False)
        if result.stdout.strip().isdigit():
            self.notification_id = result.stdout.strip()

    def progress(self, summary: str, percent: int) -> None:
        if percent - self.last_progress >= PROGRESS_STEP or percent == 100:
            self.last_progress = percent
            self.show(summary, f'{percent}%', percent)

    def offer_restart(self, summary: str, body: str) -> None:
        if not self.enabled:
            return
        ask = shlex.join(self._notify_send(summary, body, '--action', 'restart=Restart now', '--wait'))
        subprocess.Popen(['sh', '-c', f'{ask} | grep -qx restart && /usr/lib/hippos/hippos-shutdown reboot'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
