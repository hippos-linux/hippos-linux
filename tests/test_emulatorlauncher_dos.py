import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_computers as computers
import emulatorlauncher_shared as shared


class FolderProgramTests(unittest.TestCase):
    def setUp(self):
        self.game = Path(tempfile.mkdtemp()) / 'Game.pc'
        self.game.mkdir()

    def test_dosbox_bat_comes_first(self):
        (self.game / 'GAME.EXE').write_text('')
        (self.game / 'dosbox.bat').write_text('')
        self.assertEqual(shared._dos_folder_program(self.game), self.game / 'dosbox.bat')

    def test_falls_back_to_a_batch_file_then_a_program(self):
        (self.game / 'GAME.EXE').write_text('')
        self.assertEqual(shared._dos_folder_program(self.game), self.game / 'GAME.EXE')
        (self.game / 'start.bat').write_text('')
        self.assertEqual(shared._dos_folder_program(self.game), self.game / 'start.bat')

    def test_matches_upper_case_dos_names(self):
        (self.game / 'START.BAT').write_text('')
        self.assertEqual(shared._dos_folder_program(self.game), self.game / 'START.BAT')

    def test_empty_folder_has_no_program(self):
        self.assertIsNone(shared._dos_folder_program(self.game))


class StagingFolderTests(unittest.TestCase):
    def test_folder_game_is_mounted_as_c(self):
        game = Path(tempfile.mkdtemp()) / 'Game.pc'
        game.mkdir()
        (game / 'dosbox.bat').write_text('')
        (game / 'dosbox.conf').write_text('')
        ctx = SimpleNamespace(rom=game, system='dos')
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))
        with mock.patch.object(computers, '_find_emulator_bin', return_value=Path('/bin/dosbox')), \
                mock.patch.object(computers, '_load_hippos_conf', return_value={}), \
                mock.patch.object(computers, '_build_game_env', return_value={}), \
                mock.patch.object(computers, '_run_game_command', run), \
                mock.patch.object(computers, 'SAVES', Path(tempfile.mkdtemp())):
            computers.launch_dosbox_staging(ctx)
        cmd = run.call_args.args[2]
        self.assertIn(f'mount c "{game}"', cmd)
        self.assertEqual(cmd[cmd.index('--conf') + 1], str(game / 'dosbox.conf'))
        self.assertEqual(cmd[cmd.index('c:') + 2], 'dosbox.bat')


if __name__ == '__main__':
    unittest.main()
