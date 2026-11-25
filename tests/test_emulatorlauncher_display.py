import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_shared as shared


class XwaylandEnvTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.listed = Path(tmp.name) / 'xwayland-emulators'
        patcher = mock.patch.object(shared, 'EMULATORLAUNCHER_XWAYLAND', self.listed)
        patcher.start()
        self.addCleanup(patcher.stop)

    def env_for(self, emulator: str) -> dict[str, str]:
        ctx = SimpleNamespace(emulator=emulator, system='nds', rom=Path('/userdata/roms/nds/game.nds'),
                              game_wheel=None, controllers=[])
        with mock.patch.dict(shared.os.environ, {}, clear=True):
            return shared._build_game_env({}, ctx)

    def test_listed_emulator_runs_on_x11(self):
        self.listed.write_text('duckstation\nmelonds\n')
        env = self.env_for('melonds')
        self.assertEqual((env['QT_QPA_PLATFORM'], env['SDL_VIDEODRIVER']), ('xcb', 'x11'))

    def test_other_emulators_choose_for_themselves(self):
        self.listed.write_text('melonds\n')
        env = self.env_for('ppsspp')
        self.assertNotIn('QT_QPA_PLATFORM', env)
        self.assertNotIn('SDL_VIDEODRIVER', env)

    def test_missing_list_forces_nothing(self):
        self.assertNotIn('QT_QPA_PLATFORM', self.env_for('melonds'))


if __name__ == '__main__':
    unittest.main()
