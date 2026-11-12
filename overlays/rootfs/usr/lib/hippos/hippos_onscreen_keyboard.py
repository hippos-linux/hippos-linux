from __future__ import annotations

import subprocess
from contextlib import contextmanager

ACCESSIBILITY_ENV = {
    'ACCESSIBILITY_ENABLED': '1',
    'QT_ACCESSIBILITY': '1',
    'QT_LINUX_ACCESSIBILITY_ALWAYS_ON': '1',
}
KEYBOARD_BIN = '/usr/lib/hippos/hippos-osk'


@contextmanager
def onscreen_keyboard(env: dict[str, str]):
    env.update(ACCESSIBILITY_ENV)
    session_env = {key: value for key, value in env.items() if key != 'XDG_CONFIG_HOME'}
    subprocess.run(['gsettings', 'set', 'org.gnome.desktop.interface', 'toolkit-accessibility', 'true'],
                   env=session_env, capture_output=True)
    keyboard = subprocess.Popen([KEYBOARD_BIN], env=session_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        yield
    finally:
        keyboard.terminate()
        try:
            keyboard.wait(timeout=5)
        except subprocess.TimeoutExpired:
            keyboard.kill()
