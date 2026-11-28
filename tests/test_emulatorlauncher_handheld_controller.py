import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_shared as shared
from emulatorlauncher_shared import LaunchContext

ROM = Path('/userdata/roms/linuxgames/Hellpoint/Hellpoint-HippOS.sh')


def run_game(conf, fail=False):
    ctx = LaunchContext(system='linuxgames', rom=ROM, emulator='sh', core='sh')
    with mock.patch.object(shared.subprocess, 'run') as run:
        try:
            with shared.game_handheld_controller(conf, ctx):
                if fail:
                    raise RuntimeError('game failed to start')
        except RuntimeError:
            pass
    return [call.args[0][1:] for call in run.call_args_list]


class HandheldControllerTests(unittest.TestCase):
    def test_game_setting_switches_then_restores(self):
        conf = {'linuxgames["Hellpoint-HippOS.sh"].handheld_controller': 'xb360'}
        self.assertEqual(run_game(conf), [['game', 'xb360'], ['restore']])

    def test_restores_when_the_game_fails(self):
        conf = {'linuxgames.handheld_controller': 'xb360'}
        self.assertEqual(run_game(conf, fail=True), [['game', 'xb360'], ['restore']])

    def test_auto_leaves_the_controller_alone(self):
        self.assertEqual(run_game({'linuxgames["Hellpoint-HippOS.sh"].handheld_controller': 'auto'}), [])
        self.assertEqual(run_game({}), [])


if __name__ == '__main__':
    unittest.main()
