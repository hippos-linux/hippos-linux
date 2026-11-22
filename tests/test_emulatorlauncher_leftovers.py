import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

LAUNCHER_DIR = Path(__file__).resolve().parents[1] / 'overlays/rootfs/usr/lib/hippos'

SCRIPT = textwrap.dedent('''
    import subprocess, sys, time
    sys.path.insert(0, sys.argv[1])
    import emulatorlauncher_shared as shared
    shared._adopt_orphaned_game_processes()
    subprocess.run(['sh', '-c', '(sh -c "exec sleep 300" &) ; exec sleep 300 &'])
    time.sleep(0.3)
    print(len(shared._child_pids()))
    shared._stop_leftover_game_processes()
    print(len(shared._child_pids()))
''')


class LeftoverGameProcessTests(unittest.TestCase):
    def test_processes_the_game_left_running_are_stopped(self):
        result = subprocess.run([sys.executable, '-c', SCRIPT, str(LAUNCHER_DIR)],
                                capture_output=True, text=True, timeout=30, check=True)
        left_running, after_cleanup = result.stdout.split()[-2:]
        self.assertEqual(left_running, '2')
        self.assertEqual(after_cleanup, '0')


if __name__ == '__main__':
    unittest.main()
