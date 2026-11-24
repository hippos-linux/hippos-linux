import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays/rootfs/usr/lib/hippos'))

import hippos_settings  # noqa: E402


class SettingsSetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conf = Path(tmp.name) / 'hippos.conf'
        self.conf.write_text('system.session=es\nkeep=1\n')
        patcher = mock.patch.object(hippos_settings, 'USER_CONF', self.conf)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *args):
        with mock.patch.object(sys, 'argv', ['hippos-settings', *args]):
            return hippos_settings.main()

    def values(self):
        return dict(line.split('=', 1) for line in self.conf.read_text().splitlines())

    def test_single_pair(self):
        self.assertEqual(self.run_cli('set', 'system.session', 'desktop'), 0)
        self.assertEqual(self.values(), {'system.session': 'desktop', 'keep': '1'})

    def test_several_pairs_in_one_call(self):
        self.assertEqual(self.run_cli('set', 'system.desktop', 'lxqt', 'system.session', 'desktop'), 0)
        self.assertEqual(self.values(), {'system.desktop': 'lxqt', 'system.session': 'desktop', 'keep': '1'})

    def test_odd_number_of_arguments_is_rejected(self):
        self.assertEqual(self.run_cli('set', 'system.session'), 1)
        self.assertEqual(self.values(), {'system.session': 'es', 'keep': '1'})


if __name__ == '__main__':
    unittest.main()
