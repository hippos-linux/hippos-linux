import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import hippos_padtokey as padtokey


class FindKeysFilesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.system_maps = self.root / 'share'
        self.user_maps = self.root / 'user'
        self.system_maps.mkdir()
        self.user_maps.mkdir()
        (self.system_maps / 'controller-as-mouse.keys').write_text('{}')
        (self.system_maps / 'linux.keys').write_text('{}')
        self.rom = self.root / 'game.sfc'
        self.rom.write_text('')
        self.saved = padtokey.SYSTEM_MAPS, padtokey.USER_MAPS, padtokey.POINTER_MAP
        padtokey.SYSTEM_MAPS, padtokey.USER_MAPS = self.system_maps, self.user_maps
        padtokey.POINTER_MAP = self.system_maps / 'controller-as-mouse.keys'

    def tearDown(self):
        padtokey.SYSTEM_MAPS, padtokey.USER_MAPS, padtokey.POINTER_MAP = self.saved

    def test_system_map_is_used_when_defaults_are_on(self):
        self.assertEqual(padtokey.find_keys_files('linux', 'sh', self.rom, True), [self.system_maps / 'linux.keys'])

    def test_pointer_falls_back_to_shared_map_for_systems_without_one(self):
        self.assertEqual(padtokey.find_keys_files('snes', 'retroarch', self.rom, True), [])
        self.assertEqual(padtokey.find_keys_files('snes', 'retroarch', self.rom, True, pointer=True),
                         [padtokey.POINTER_MAP])

    def test_pointer_off_keeps_only_the_game_map(self):
        game_map = self.root / 'game.sfc.keys'
        game_map.write_text('{}')
        self.assertEqual(padtokey.find_keys_files('linux', 'sh', self.rom, False), [game_map])


if __name__ == '__main__':
    unittest.main()
