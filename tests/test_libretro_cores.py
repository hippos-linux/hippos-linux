import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import yaml

from libretro_cores import REPLACED_CORES, core_file_names

DESCRIPTOR = Path(__file__).resolve().parent.parent / 'packages' / 'emulators' / 'retroarch' / 'retroarch.emulator.yml'


class CoreFileNamesTests(unittest.TestCase):
    def test_plain_core(self):
        self.assertEqual(core_file_names('snes9x'), ('snes9x_libretro.so',))

    def test_alias(self):
        self.assertEqual(core_file_names('bsnes_hd'), ('bsnes_hd_libretro.so', 'bsnes_hd_beta_libretro.so'))

    def test_replaced_core_falls_back_after_its_own_file(self):
        self.assertEqual(core_file_names('snes9x2010'), ('snes9x2010_libretro.so', 'snes9x_libretro.so'))


class ReplacedCoresTests(unittest.TestCase):
    def test_replacements_are_offered_cores_not_replaced_ones(self):
        listed: dict[str, set[str]] = {}
        for system in yaml.safe_load(DESCRIPTOR.read_text())['systems']:
            cores = system.get('as_core') or []
            for core in cores if isinstance(cores, list) else [cores]:
                listed.setdefault(str(core), set()).add(system['name'])
        for old, new in REPLACED_CORES.items():
            self.assertNotIn(old, REPLACED_CORES.values(), old)
            self.assertIn(new, listed, f'{old} -> {new}')


if __name__ == '__main__':
    unittest.main()
