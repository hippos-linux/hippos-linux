import importlib.machinery
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LIB = Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'
sys.path.insert(0, str(LIB))


def _load_cli():
    loader = importlib.machinery.SourceFileLoader('hippos_padtokey_cli', str(LIB / 'hippos-padtokey'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


cli = _load_cli()


class KeyLabelTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(cli.key_label('KEY_A'), 'A')
        self.assertEqual(cli.key_label('KEY_SPACE'), 'Space')
        self.assertEqual(cli.key_label('KEY_KP5'), 'Keypad 5')
        self.assertEqual(cli.key_label('BTN_LEFT'), 'Mouse left')


class EditTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.rom = self.folder / 'game.zip'
        self.rom.write_text('')
        system_keys = self.folder / 'system.keys'
        system_keys.write_text(json.dumps({'actions_player1': [
            {'trigger': 'a', 'type': 'key', 'target': 'KEY_ENTER'},
            {'trigger': 'joystick1', 'type': 'mouse'}]}))
        game = {'system': 'dos', 'emulator': 'dosbox', 'rom': str(self.rom), 'controllers': []}
        for name, value in (('running_game', lambda: game), ('reapply_running_game', lambda: True),
                            ('find_keys_files', lambda *a, **k: [system_keys])):
            patcher = mock.patch.object(cli, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_first_edit_copies_the_system_profile_into_the_game_file(self):
        cli.set_keys(self.rom, 'b', ['KEY_SPACE'])
        saved = json.loads((self.folder / 'game.zip.keys').read_text())['actions_player1']
        self.assertIn({'trigger': 'a', 'type': 'key', 'target': 'KEY_ENTER'}, saved)
        self.assertIn({'trigger': 'joystick1', 'type': 'mouse'}, saved)
        self.assertEqual(cli.get(self.rom, 'b'), 'Space')

    def test_combination_is_saved_as_a_list_with_modifiers_first(self):
        cli.set_keys(self.rom, 'b', ['KEY_C', 'KEY_LEFTCTRL'])
        saved = json.loads((self.folder / 'game.zip.keys').read_text())['actions_player1']
        self.assertIn({'trigger': 'b', 'type': 'key', 'target': ['KEY_LEFTCTRL', 'KEY_C'],
                       'description': 'Left Ctrl + C'}, saved)
        self.assertEqual(cli.get(self.rom, 'b'), 'Left Ctrl + C')

    def test_not_mapped_removes_the_input(self):
        cli.set_keys(self.rom, 'a', [])
        self.assertEqual(cli.get(self.rom, 'a'), '')


class KeyPickerTests(unittest.TestCase):
    def test_keyboard_offers_exactly_the_editor_keys(self):
        import hippos_keypicker as picker
        offered = {key for rows in (picker.MAIN_ROWS, picker.NAV_ROWS, picker.EXTRA_ROWS)
                   for row in rows for _label, key, _width in row if key}
        self.assertEqual(offered, set(cli.KEYS) | {'none'})


if __name__ == '__main__':
    unittest.main()
