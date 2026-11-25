import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest import mock

HIPPOS_LIB = Path(__file__).resolve().parent.parent / 'overlays/rootfs/usr/lib/hippos'
sys.path.insert(0, str(HIPPOS_LIB))

import hippos_port_games  # noqa: E402
from hippos_launcher_sync import GameMetadata, update_gamelist  # noqa: E402
from hippos_port_games import ELF_MACHINES, PORT_GAMES, find_games, hidden_data_files  # noqa: E402


def _load_sync():
    loader = importlib.machinery.SourceFileLoader('hippos_port_games_sync', str(HIPPOS_LIB / 'hippos-port-games-sync'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def games_for(system):
    return tuple(game for game in PORT_GAMES if game.system == system)


class PortGamesTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.roms = self.base / 'roms'

    def system(self, name, *files):
        folder = self.roms / name
        for relative in files:
            (folder / relative).parent.mkdir(parents=True, exist_ok=True)
            (folder / relative).write_bytes(b'')
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def found(self, name):
        return {path.relative_to(self.roms / name).as_posix(): game.title
                for path, game in find_games(self.roms / name, games_for(name)).items()}

    def test_fallout_found_whatever_the_case_of_its_files(self):
        self.system('fallout1-ce', 'master.dat', 'Critter.DAT')
        self.assertEqual(self.found('fallout1-ce'), {'Fallout.f1ce': 'Fallout'})

    def test_nothing_found_without_all_the_files(self):
        self.system('fallout1-ce', 'MASTER.DAT')
        self.assertEqual(self.found('fallout1-ce'), {})

    def test_existing_launcher_is_used(self):
        self.system('fallout2-ce', 'master.dat', 'critter.dat', 'My Fallout 2.f2ce')
        self.assertEqual(self.found('fallout2-ce'), {'My Fallout 2.f2ce': 'Fallout 2'})

    def test_sonic_retro_games_told_apart_by_folder_name(self):
        self.system('sonicretro', 'Sonic CD/Data.rsdk', 'Sonic 2/Data.rsdk', 'Sonic 1/Data.rsdk', 'Data.rsdk')
        self.assertEqual(self.found('sonicretro'), {
            'Sonic CD/Sonic CD.scd': 'Sonic CD',
            'Sonic 2/Sonic the Hedgehog 2.son': 'Sonic the Hedgehog 2',
            'Sonic 1/Sonic the Hedgehog.son': 'Sonic the Hedgehog',
        })

    def test_keen_episodes_found_by_their_executable(self):
        self.system('cgenius', 'Keen1/KEEN1.EXE', 'Keen4/KEEN4E.EXE', 'Dreams/kdreams.exe')
        self.assertEqual(set(self.found('cgenius').values()), {
            'Commander Keen 1: Marooned on Mars',
            'Commander Keen 4: Secret of the Oracle',
            'Commander Keen in Keen Dreams',
        })

    def test_jazz2_needs_its_source_folder(self):
        self.system('jazz2', 'Anims.j2a')
        self.assertEqual(self.found('jazz2'), {})
        self.system('jazz2', 'Source/anims.J2A')
        self.assertEqual(self.found('jazz2'), {'Jazz Jackrabbit 2.game': 'Jazz Jackrabbit 2'})

    def test_quake2_and_its_mission_packs_use_their_own_data_files(self):
        self.system('quake2', 'baseq2/pak0.pak', 'baseq2/pak1.pak', 'rogue/pak0.pak', 'xatrix/PAK0.PAK')
        found = find_games(self.roms / 'quake2', games_for('quake2'))
        entries = {path.relative_to(self.roms / 'quake2').as_posix(): game for path, game in found.items()}
        self.assertEqual({path: game.metadata.core for path, game in entries.items()}, {
            'baseq2/pak0.pak': 'vitaquake2',
            'rogue/pak0.pak': 'vitaquake2-rogue',
            'xatrix/PAK0.PAK': 'vitaquake2-xatrix',
        })
        self.assertEqual([path.name for path in hidden_data_files(found)], ['pak1.pak'])

    def test_tomb_raider_shows_the_title_and_hides_the_levels(self):
        self.system('openlara', 'Tomb Raider/DATA/GYM.PHD', 'Tomb Raider/DATA/TITLE.PHD', 'Tomb Raider/DATA/LEVEL1.PHD')
        found = find_games(self.roms / 'openlara', games_for('openlara'))
        self.assertEqual(self.found('openlara'), {'Tomb Raider/DATA/TITLE.PHD': 'Tomb Raider'})
        self.assertEqual(sorted(path.name for path in hidden_data_files(found)), ['GYM.PHD', 'LEVEL1.PHD'])

    def test_gamelist_entry_in_a_subfolder_gets_every_field(self):
        folder = self.system('sonicretro', 'Sonic CD/Data.rsdk')
        launcher = folder / 'Sonic CD/Sonic CD.scd'
        launcher.write_text('x')
        art = self.base / 'logo.png'
        art.write_bytes(b'png')
        metadata = GameMetadata('Sonic CD', 'About', 'Sonic Team', None, 'Sega', '20110101T000000', 'Platform', '1',
                                marquee=art)
        update_gamelist(folder, '.scd', {launcher: metadata})
        game = ET.parse(folder / 'gamelist.xml').getroot().find('game')
        self.assertEqual(game.findtext('path'), './Sonic CD/Sonic CD.scd')
        self.assertEqual(game.findtext('publisher'), 'Sega')
        self.assertEqual(game.findtext('releasedate'), '20110101T000000')
        self.assertEqual(game.findtext('marquee'), './images/Sonic CD - Sonic CD-marquee.png')
        self.assertTrue((folder / 'images/Sonic CD - Sonic CD-marquee.png').is_file())


class PortGamesSyncTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        self.base = base
        self.roms = base / 'roms'
        self.sync_module = _load_sync()
        patches = (
            mock.patch.object(self.sync_module, 'ROMS', self.roms),
            mock.patch.object(self.sync_module, 'STATE_FILE', base / 'state.json'),
            mock.patch.object(self.sync_module, 'download_steam_art', return_value=(None, None)),
            mock.patch.object(self.sync_module, 'reload_es'),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_launcher_appears_with_the_game_and_goes_with_it(self):
        folder = self.roms / 'sonic-mania'
        folder.mkdir(parents=True)
        data = folder / 'Data.rsdk'
        data.write_bytes(b'')
        self.sync_module.sync()
        launcher = folder / 'Sonic Mania.sman'
        self.assertTrue(launcher.is_file())
        game = ET.parse(folder / 'gamelist.xml').getroot().find('game')
        self.assertEqual(game.findtext('developer'), 'Christian Whitehead, Headcannon, PagodaWest Games')

        data.unlink()
        self.sync_module.sync()
        self.assertFalse(launcher.exists())
        self.assertIsNone(ET.parse(folder / 'gamelist.xml').getroot().find('game'))

    def test_data_files_hidden_and_core_set_in_the_gamelist(self):
        folder = self.roms / 'quake2'
        for name in ('baseq2/pak0.pak', 'baseq2/pak1.pak'):
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(b'')
        self.sync_module.sync()
        games = {game.findtext('path'): game for game in ET.parse(folder / 'gamelist.xml').getroot().findall('game')}
        self.assertEqual(games['./baseq2/pak0.pak'].findtext('name'), 'Quake II')
        self.assertEqual(games['./baseq2/pak0.pak'].findtext('core'), 'vitaquake2')
        self.assertIsNone(games['./baseq2/pak0.pak'].find('hidden'))
        self.assertEqual(games['./baseq2/pak1.pak'].findtext('hidden'), 'true')
        self.assertTrue((folder / 'baseq2/pak0.pak').read_bytes() == b'')

    def test_voxatron_player_installed_from_its_zip_then_splore_appears(self):
        folder = self.roms / 'voxatron'
        folder.mkdir(parents=True)
        player = self.base / 'bios/voxatron/vox'
        elf = b'\x7fELF' + bytes(14) + ELF_MACHINES[hippos_port_games.platform.machine()].to_bytes(2, 'little')
        with zipfile.ZipFile(folder / 'voxatron_amd64.zip', 'w') as bundle:
            bundle.writestr('voxatron/vox', elf)
            bundle.writestr('voxatron/vox.dat', b'data')
        games = tuple(replace(game, requires=player) if game.system == 'voxatron' else game for game in PORT_GAMES)
        with mock.patch.object(hippos_port_games, 'VOXATRON_PLAYER', player), \
                mock.patch.object(self.sync_module, 'PORT_GAMES', games):
            self.sync_module.sync()
        self.assertTrue(player.is_file())
        self.assertTrue((player.parent / 'vox.dat').is_file())
        game = ET.parse(folder / 'gamelist.xml').getroot().find('game')
        self.assertEqual(game.findtext('path'), './Splore.vox')
        self.assertEqual(game.findtext('name'), 'Voxatron')

    def test_users_own_launcher_is_never_deleted(self):
        folder = self.roms / 'sonic-mania'
        folder.mkdir(parents=True)
        own = folder / 'Mania.sman'
        own.write_text('')
        self.sync_module.sync()
        self.assertTrue(own.exists())


if __name__ == '__main__':
    unittest.main()
