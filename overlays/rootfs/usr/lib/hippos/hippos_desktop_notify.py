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
        self.task = ''
        self.last_progress = -PROGRESS_STEP

    def _as_session_user(self, *command: str) -> list[str]:
        uid = pwd.getpwnam(SESSION_USER).pw_uid
        return ['runuser', '-u', SESSION_USER, '--', 'env',
                f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus', f'XDG_RUNTIME_DIR=/run/user/{uid}',
                *command]

    def _notify_send(self, summary: str, body: str, *options: str) -> list[str]:
        replace = ['--replace-id', self.notification_id] if self.notification_id else []
        return ['notify-send', '--app-name', APP_NAME, '--icon', ICON, '--print-id', *replace, *options,
                summary, body]

    def show(self, summary: str, body: str = '', progress: int | None = None) -> None:
        if not self.enabled:
            return
        hint = ['--hint', f'int:value:{progress}'] if progress is not None else []
        result = subprocess.run(self._as_session_user(*self._notify_send(summary, body, *hint)),
                                capture_output=True, text=True, check=False)
        if result.stdout.strip().isdigit():
            self.notification_id = result.stdout.strip()

    def begin(self, task: str, body: str = '') -> None:
        self.task = task
        self.last_progress = -PROGRESS_STEP
        self.show(task, body, 0)

    def progress(self, percent: int) -> None:
        if self.task and (percent - self.last_progress >= PROGRESS_STEP or percent == 100):
            self.last_progress = percent
            self.show(self.task, f'{percent}%', percent)

    def ask(self, summary: str, body: str, actions: dict[str, str]) -> None:
        if not self.enabled:
            return
        options = [option for index, label in enumerate(actions) for option in ('--action', f'a{index}={label}')]
        prompt = shlex.join(self._notify_send(summary, body, *options, '--wait'))
        cases = ' '.join(f'a{index}) {command} ;;' for index, command in enumerate(actions.values()))
        subprocess.run(self._as_session_user('systemd-run', '--user', '--collect', '--quiet', 'sh', '-c',
                                             f'case "$({prompt} | tail -n 1)" in {cases} esac'),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    def offer_restart(self, summary: str, body: str) -> None:
        self.ask(summary, body, {'Restart now': 'sudo /usr/lib/hippos/hippos-shutdown reboot'})
