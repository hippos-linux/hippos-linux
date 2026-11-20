import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_shared as shared


class GamescopeWrapTests(unittest.TestCase):
    def setUp(self):
        self.ctx = SimpleNamespace(system='ports', rom=Path('/userdata/roms/ports/Game.sh'), monitor=-1)
        patcher = mock.patch.object(shared, 'which', return_value='/usr/games/gamescope')
        patcher.start()
        self.addCleanup(patcher.stop)

    def wrap(self, conf):
        return shared._gamescope_wrap(['game'], conf, self.ctx)

    def test_off_by_default(self):
        self.assertEqual(self.wrap({}), ['game'])

    def test_global_setting_applies(self):
        self.assertEqual(self.wrap({'global.gamescope': '1'}),
                         ['/usr/games/gamescope', '-f', '-e', '--', 'game'])

    def test_game_setting_applies_without_global(self):
        conf = {'ports["Game.sh"].gamescope': '1', 'ports.gamescope_scaler': 'integer'}
        self.assertEqual(self.wrap(conf),
                         ['/usr/games/gamescope', '-S', 'integer', '-f', '-e', '--', 'game'])

    def test_game_setting_overrides_global(self):
        conf = {'global.gamescope': '1', 'ports["Game.sh"].gamescope': '0'}
        self.assertEqual(self.wrap(conf), ['game'])

    def test_system_resolution_overrides_global(self):
        conf = {'global.gamescope': '1',
                'global.gamescope_output_resolution': '1280x720',
                'ports.gamescope_output_resolution': '1920x1080'}
        self.assertEqual(self.wrap(conf)[1:5], ['-W', '1920', '-H', '1080'])


if __name__ == '__main__':
    unittest.main()
