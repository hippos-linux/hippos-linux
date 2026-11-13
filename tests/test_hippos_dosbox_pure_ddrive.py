import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'
sys.path.insert(0, str(LIB))

import hippos_dosbox_pure_ddrive as ddrive  # noqa: E402

AOE_BIN = 'Age of Empires - Gold Edition (USA) (Rerelease) (Alt).bin'
AOE_CUE = 'Age of Empires - Gold Edition (USA) (Rerelease) (Alt).cue'
AOE_DATE = (1996, 12, 24, 23, 32, 0)


class DosNameTests(unittest.TestCase):
    def test_long_names_keep_four_characters_from_each_end(self):
        self.assertEqual(ddrive.dos_name(AOE_BIN), b'AGE-ALT).BIN')

    def test_valid_short_names_are_unchanged(self):
        self.assertEqual(ddrive.dos_name('SETUP.EXE'), b'SETUP.EXE')


class DriveHashTests(unittest.TestCase):
    def setUp(self):
        self.entries = [ddrive._entry(b'AGE-ALT).BIN', 323929200, AOE_DATE)]

    def test_matches_the_save_dosbox_pure_made_at_1_gb(self):
        self.assertEqual(ddrive.drive_hash(self.entries, '1024'), 0x12AA48FC)

    def test_matches_the_save_a_pack_made_at_2_gb(self):
        self.assertEqual(ddrive.drive_hash(self.entries, '2048'), 0x5C47A3A5)

    def test_empty_drive_at_1_gb_has_no_hash_in_its_name(self):
        self.assertEqual(ddrive.drive_hash([], '1024'), 0x11111111)


class FreeSpaceForTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.roms, self.saves = root / 'roms', root / 'saves'
        self.roms.mkdir()
        self.saves.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _cd_game(self, stem):
        rom = self.roms / f'{stem}.zip'
        with zipfile.ZipFile(rom, 'w') as archive:
            archive.writestr(zipfile.ZipInfo(AOE_CUE, AOE_DATE), f'FILE "{AOE_BIN}" BINARY\n')
            archive.writestr(zipfile.ZipInfo(AOE_BIN, AOE_DATE), b'x' * 16)
        return rom

    def _save(self, rom, free_space):
        entries = ddrive.hashed_entries(rom, self.saves / f'{rom.stem}.pure.zip')
        (self.saves / f'{rom.stem}-{ddrive.drive_hash(entries, free_space):08X}.sav').write_bytes(b'FFDD\x01')

    def test_game_without_saves_uses_the_default(self):
        self.assertEqual(ddrive.free_space_for(self._cd_game('New'), self.saves), '1024')

    def test_existing_install_selects_its_free_space(self):
        rom = self._cd_game('Pack Game')
        self._save(rom, '2048')
        self.assertEqual(ddrive.free_space_for(rom, self.saves), '2048')

    def test_cue_is_left_out_of_the_hash_and_its_track_is_counted(self):
        entries = ddrive.hashed_entries(self._cd_game('Game'), self.saves / 'none.pure.zip')
        self.assertEqual([path for path, _ in entries], [b'AGE-ALT).BIN'])

    def test_unmatched_install_uses_what_the_other_games_use(self):
        for stem in ('A', 'B'):
            self._save(self._cd_game(stem), '4096')
        folder = self.roms / 'Folder Game.zip'
        with zipfile.ZipFile(folder, 'w') as archive:
            archive.writestr('GAME/SETUP.EXE', b'x')
        (self.saves / 'Folder Game-0BADF00D.sav').write_bytes(b'FFDD\x01')
        self.assertEqual(ddrive.free_space_for(folder, self.saves), '4096')


if __name__ == '__main__':
    unittest.main()
