import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT_PATH = (Path(__file__).resolve().parent.parent
               / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos' / 'hippos-storage-manager')


def _load_storage_manager():
    loader = importlib.machinery.SourceFileLoader('hippos_storage_manager', str(SCRIPT_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


sm = _load_storage_manager()
CREDENTIALS = 'credentials=/userdata/system/configs/hippos/credentials/nas_Games.cred'


class NetworkSavesTests(unittest.TestCase):
    def test_saves_are_written_back_unless_turned_off(self):
        self.assertTrue(sm.network_saves_writable('cifs://nas/Games'))
        self.assertTrue(sm.network_saves_writable(f'cifs://nas/Games {CREDENTIALS}'))
        self.assertFalse(sm.network_saves_writable(f'cifs://nas/Games {CREDENTIALS},saves=ro'))
        self.assertFalse(sm.network_saves_writable('nfs:nas:/export saves=ro'))

    def test_turning_off_keeps_other_mount_options(self):
        self.assertEqual(sm.with_network_saves(f'cifs://nas/Games {CREDENTIALS}', False),
                         f'cifs://nas/Games {CREDENTIALS},saves=ro')
        self.assertEqual(sm.with_network_saves('nfs:nas:/export', False), 'nfs:nas:/export saves=ro')

    def test_turning_on_removes_the_option(self):
        self.assertEqual(sm.with_network_saves(f'cifs://nas/Games {CREDENTIALS},saves=ro', True),
                         f'cifs://nas/Games {CREDENTIALS}')
        self.assertEqual(sm.with_network_saves('nfs:nas:/export saves=ro', True), 'nfs:nas:/export')

    def test_mount_path_ignores_options(self):
        self.assertEqual(sm.network_mount_path('nfs:nas:/export saves=ro'), Path('/media/nas_export'))
        self.assertEqual(sm.network_mount_path(f'cifs://nas/Games {CREDENTIALS}'), Path('/media/nas_Games'))


if __name__ == '__main__':
    unittest.main()
