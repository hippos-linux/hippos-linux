"""Tests for moving saves to their per-system and per-emulator folders."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays/rootfs/usr/lib/hippos'))

import hippos_save_migration as saves_migration  # noqa: E402

ES_SYSTEMS = """<systemList>
  <system><name>megadrive</name><emulators><emulator name="libretro"><cores><core>genesis_plus_gx</core></cores></emulator></emulators></system>
  <system><name>mastersystem</name><emulators><emulator name="libretro"><cores><core>genesis_plus_gx</core></cores></emulator></emulators></system>
  <system><name>win98</name><emulators><emulator name="retroarch"><cores><core>dosbox_pure</core></cores></emulator></emulators></system>
  <system><name>anarch</name><emulators><emulator name="libretro"><cores><core>anarch</core></cores></emulator></emulators></system>
</systemList>"""


class MigrateTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.saves, self.roms, self.info = self.base / 'saves', self.base / 'roms', self.base / 'info'
        for path in (self.saves, self.roms, self.info):
            path.mkdir()
        for core, name in (('genesis_plus_gx', 'Genesis Plus GX'), ('dosbox_pure', 'DOSBox-pure'), ('anarch', 'anarch')):
            (self.info / f'{core}_libretro.info').write_text(f'corename = "{name}"\n')
        self.es_systems = self.base / 'es_systems.cfg'
        self.es_systems.write_text(ES_SYSTEMS)

    def rom(self, system, name):
        (self.roms / system).mkdir(exist_ok=True)
        (self.roms / system / name).write_bytes(b'')

    def save(self, folder, name):
        (self.saves / folder).mkdir(exist_ok=True)
        (self.saves / folder / name).write_bytes(b'save')
        return self.saves / folder / name

    def migrate(self):
        saves_migration.move_retroarch_core_folders(self.saves, self.roms, self.es_systems, self.info)

    def test_moves_save_and_states_for_single_system_core(self):
        self.rom('win98', 'Game (1998).zip')
        self.save('DOSBox-pure', 'Game (1998).pure.zip')
        self.save('DOSBox-pure', 'Game (1998)-CDRIVE.sav')
        self.migrate()
        self.assertTrue((self.saves / 'win98' / 'Game (1998).pure.zip').exists())
        self.assertTrue((self.saves / 'win98' / 'Game (1998)-CDRIVE.sav').exists())
        self.assertFalse((self.saves / 'DOSBox-pure').exists())

    def test_shared_core_uses_the_system_that_has_the_rom(self):
        self.rom('mastersystem', 'Sonic.sms')
        self.rom('megadrive', 'Streets.md')
        self.save('Genesis Plus GX', 'Sonic.srm')
        self.save('Genesis Plus GX', 'Streets.state1')
        self.migrate()
        self.assertTrue((self.saves / 'mastersystem' / 'Sonic.srm').exists())
        self.assertTrue((self.saves / 'megadrive' / 'Streets.state1').exists())

    def test_name_in_two_systems_stays(self):
        self.rom('mastersystem', 'Sonic.sms')
        self.rom('megadrive', 'Sonic.md')
        left = self.save('Genesis Plus GX', 'Sonic.srm')
        self.migrate()
        self.assertTrue(left.exists())

    def test_existing_target_is_not_overwritten(self):
        self.rom('megadrive', 'Streets.md')
        (self.saves / 'megadrive').mkdir()
        (self.saves / 'megadrive' / 'Streets.srm').write_bytes(b'mine')
        left = self.save('Genesis Plus GX', 'Streets.srm')
        self.migrate()
        self.assertTrue(left.exists())
        self.assertEqual((self.saves / 'megadrive' / 'Streets.srm').read_bytes(), b'mine')

    def test_folder_named_like_a_system_is_untouched(self):
        self.rom('anarch', 'anarch.game')
        kept = self.save('anarch', 'anarch.srm')
        self.migrate()
        self.assertTrue(kept.exists())

    def test_unknown_folders_are_untouched(self):
        kept = self.save('Cemu', 'mlc01.bin')
        self.migrate()
        self.assertTrue(kept.exists())


class EmulatorFoldersTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.userdata = Path(directory.name)
        (self.userdata / 'saves').mkdir()

    def write(self, relative, data=b'x'):
        path = self.userdata / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_moves_emulator_data_to_batocera_folders(self):
        self.write('system/configs/duckstation/memcards/Game_1.mcd')
        self.write('system/configs/duckstation/savestates/SLUS-1_resume.sav')
        self.write('.local/share/dolphin-emu/GC/USA/Card A/x.gci')
        self.write('.local/share/flycast/vmu_save_A1.bin')
        self.write('system/configs/rpcs3/dev_hdd0/home/00000001/savedata/S/PARAM.SFO')
        saves_migration.move_emulator_folders(self.userdata)
        saves = self.userdata / 'saves'
        for relative in ('duckstation/memcards/Game_1.mcd', 'duckstation/SLUS-1_resume.sav',
                         'dolphin-emu/GC/USA/Card A/x.gci', 'dreamcast/flycast/vmu_save_A1.bin',
                         'ps3/rpcs3/dev_hdd0/home/00000001/savedata/S/PARAM.SFO'):
            self.assertTrue((saves / relative).exists(), relative)
        self.assertFalse((self.userdata / '.local/share/flycast').exists())

    def test_existing_files_win_and_source_is_kept(self):
        self.write('saves/dreamcast/flycast/vmu_save_A1.bin', b'new')
        left = self.write('.local/share/flycast/vmu_save_A1.bin', b'old')
        saves_migration.move_emulator_folders(self.userdata)
        self.assertEqual((self.userdata / 'saves/dreamcast/flycast/vmu_save_A1.bin').read_bytes(), b'new')
        self.assertTrue(left.exists())

    def test_mame_states_move_under_state(self):
        self.write('saves/mame/sf2/1.sta')
        self.write('saves/mame/nvram/sf2/eeprom')
        self.write('saves/mame/fmtowns/disk.img')
        saves_migration.move_emulator_folders(self.userdata)
        saves = self.userdata / 'saves' / 'mame'
        self.assertTrue((saves / 'state/sf2/1.sta').exists())
        self.assertTrue((saves / 'nvram/sf2/eeprom').exists())
        self.assertTrue((saves / 'fmtowns/disk.img').exists())


if __name__ == '__main__':
    unittest.main()
