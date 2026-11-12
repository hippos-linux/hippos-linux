import os
import subprocess
import sys
from pathlib import Path

INSTALLERS_DIR = Path('/usr/lib/hippos/content-installers')


def run(name: str, action: str) -> int:
    if not name or '/' in name or name.startswith('.'):
        print(f'Invalid installer name: {name}', file=sys.stderr)
        return 1
    script = INSTALLERS_DIR / name
    if not script.is_file() or not os.access(script, os.X_OK):
        print(f'Installer not found: {script}', file=sys.stderr)
        return 1
    cmd = [str(script), action]
    if os.getuid() != 0:
        cmd = ['sudo', '-n'] + cmd
    return subprocess.run(cmd).returncode
