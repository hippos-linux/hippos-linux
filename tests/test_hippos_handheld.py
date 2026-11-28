import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_PATH = (Path(__file__).resolve().parent.parent
               / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos' / 'hippos-handheld')
sys.path.insert(0, str(SCRIPT_PATH.parent))


def _load_hippos_handheld():
    loader = importlib.machinery.SourceFileLoader('hippos_handheld', str(SCRIPT_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


hh = _load_hippos_handheld()


def _handheld(targets, profile='/usr/share/inputplumber/profiles/default.yaml'):
    return hh.Handheld(path='/org/shadowblip/InputPlumber/CompositeDevice0', persistent_id='ayaneo:2 rev.1',
                       name='AYANEO\n2', targets=targets, profile_path=profile)


class HandheldTests(unittest.TestCase):
    def test_setting_id_is_safe_for_settings_keys(self):
        self.assertEqual(_handheld([]).setting_id, 'ayaneo_2_rev_1')

    def test_gamepad_is_first_gamepad_target(self):
        self.assertEqual(_handheld(['keyboard', 'ds5', 'mouse']).gamepad, 'ds5')
        self.assertEqual(_handheld(['keyboard', 'mouse']).gamepad, '')

    def test_with_gamepad_keeps_keyboard_and_mouse(self):
        self.assertEqual(hh.with_gamepad(['xbox-elite', 'keyboard', 'mouse'], 'deck'), ['deck', 'keyboard', 'mouse'])


class SettingLinesTests(unittest.TestCase):
    def test_lists_controller_and_profile_per_handheld(self):
        profiles = {'/usr/share/inputplumber/profiles/default.yaml': 'Default'}
        rows = [line.split('\t') for line in hh.setting_lines([_handheld(['xbox-elite', 'keyboard'])], profiles)]
        self.assertEqual(rows[0][:3], ['group', 'ayaneo_2_rev_1', 'AYANEO 2'])
        self.assertEqual(rows[1][:4], ['multiple', 'ayaneo_2_rev_1.controller', 'CONTROLLER TYPE', 'xbox-elite'])
        self.assertIn('ds5=DualSense', rows[1][4])
        self.assertEqual(rows[2][1], 'ayaneo_2_rev_1.profile')
        self.assertEqual(rows[2][4], '/usr/share/inputplumber/profiles/default.yaml=Default')

    def test_no_controller_row_without_gamepad_target(self):
        rows = [line.split('\t')[1] for line in hh.setting_lines([_handheld(['keyboard'])], {})]
        self.assertEqual(rows, ['ayaneo_2_rev_1'])


class ChoiceLinesTests(unittest.TestCase):
    def test_choices_pair_labels_with_settings(self):
        lines = hh.setting_lines([_handheld(['xbox-elite', 'keyboard'])], {'/p/default.yaml': 'Default'})
        self.assertIn('DualSense\tayaneo_2_rev_1.controller=ds5', hh.choice_lines(lines, 'controller'))
        self.assertEqual(hh.choice_lines(lines, 'profile'), ['Default\tayaneo_2_rev_1.profile=/p/default.yaml'])

    def test_labels_name_the_device_when_there_are_several(self):
        second = hh.Handheld('/x', 'other', 'Legion Go', ['ds5'], '')
        lines = hh.setting_lines([_handheld(['xbox-elite']), second], {})
        self.assertIn('Steam Deck (Legion Go)\tother.controller=deck', hh.choice_lines(lines, 'controller'))


class ProfileTests(unittest.TestCase):
    def test_profiles_use_their_name_and_skip_debug_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'default.yaml').write_text('version: 1\nname: Default\n')
            (root / 'mine.yaml').write_text('version: 1\n')
            (root / 'debug.yaml').write_text('name: Debug\n')
            profiles = hh.available_profiles((root, root / 'missing'))
        self.assertEqual(profiles, {str(root / 'default.yaml'): 'Default', str(root / 'mine.yaml'): 'mine'})


class FakePlumber:
    def __init__(self, targets):
        self.device = _handheld(targets)
        self.switched = []

    def handhelds(self):
        return [self.device]

    def set_gamepad(self, handheld, gamepad):
        self.switched.append(gamepad)
        self.device = _handheld(hh.with_gamepad(self.device.targets, gamepad))

    def wait_for_gamepad(self, path, gamepad):
        return self.device.gamepad == gamepad


class GameControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        restore_dir = mock.patch.object(hh, 'GAME_RESTORE_DIR', Path(self.tmp.name))
        restore_dir.start()
        self.addCleanup(restore_dir.stop)

    def run_with(self, plumber, *argv):
        with mock.patch.object(hh, 'InputPlumber', return_value=plumber):
            return hh.main(list(argv))

    def test_game_switches_and_restore_puts_back_the_previous_type(self):
        plumber = FakePlumber(['xbox-elite', 'mouse', 'keyboard'])
        self.assertEqual(self.run_with(plumber, 'game', 'xb360'), 0)
        self.assertEqual(plumber.device.targets, ['xb360', 'mouse', 'keyboard'])
        self.assertEqual(self.run_with(plumber, 'restore'), 0)
        self.assertEqual(plumber.device.targets, ['xbox-elite', 'mouse', 'keyboard'])
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_second_game_after_a_crash_keeps_the_original_type(self):
        plumber = FakePlumber(['xbox-elite', 'keyboard'])
        self.run_with(plumber, 'game', 'xb360')
        self.run_with(plumber, 'game', 'ds5')
        self.run_with(plumber, 'restore')
        self.assertEqual(plumber.device.gamepad, 'xbox-elite')

    def test_game_already_on_the_type_changes_nothing(self):
        plumber = FakePlumber(['xb360', 'keyboard'])
        self.run_with(plumber, 'game', 'xb360')
        self.assertEqual(plumber.switched, [])
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_restore_without_a_game_switch_does_not_contact_inputplumber(self):
        with mock.patch.object(hh, 'InputPlumber', side_effect=AssertionError):
            self.assertEqual(hh.main(['restore']), 0)

    def test_choice_made_during_the_game_is_kept_after_it(self):
        plumber = FakePlumber(['xbox-elite', 'keyboard'])
        self.run_with(plumber, 'game', 'xb360')
        with mock.patch.object(hh, '_save'):
            self.run_with(plumber, 'set', f'{plumber.device.setting_id}.controller=ds5')
        self.run_with(plumber, 'restore')
        self.assertEqual(plumber.device.gamepad, 'ds5')

    def run_this_game(self, plumber, *argv, saved=''):
        game = {'system': 'linuxgames', 'rom': '/userdata/roms/linuxgames/Hellpoint/Hellpoint.sh'}
        with mock.patch('hippos_padtokey.running_game', return_value=game), \
                mock.patch.object(hh, '_saved', return_value=saved), \
                mock.patch.object(hh, '_save') as save, mock.patch.object(hh, '_forget') as forget:
            self.assertEqual(self.run_with(plumber, 'this-game', *argv), 0)
        return save, forget

    def test_this_game_saves_the_game_setting_and_switches_now(self):
        plumber = FakePlumber(['xbox-elite', 'keyboard'])
        save, _ = self.run_this_game(plumber, 'xb360')
        save.assert_called_once_with('linuxgames["Hellpoint.sh"].handheld_controller', 'xb360')
        self.assertEqual(plumber.device.gamepad, 'xb360')
        self.run_with(plumber, 'restore')
        self.assertEqual(plumber.device.gamepad, 'xbox-elite')

    def test_this_game_auto_forgets_the_setting_and_switches_back(self):
        plumber = FakePlumber(['xbox-elite', 'keyboard'])
        self.run_this_game(plumber, 'xb360')
        _, forget = self.run_this_game(plumber, 'auto')
        forget.assert_called_once_with('linuxgames["Hellpoint.sh"].handheld_controller')
        self.assertEqual(plumber.device.gamepad, 'xbox-elite')

    def test_this_game_without_a_running_game_fails(self):
        with mock.patch('hippos_padtokey.running_game', return_value=None):
            self.assertEqual(hh.main(['this-game', 'xb360']), 1)

    def test_restore_keeps_the_record_until_the_switch_back_is_seen(self):
        plumber = FakePlumber(['xbox-elite', 'keyboard'])
        self.run_with(plumber, 'game', 'xb360')
        with mock.patch.object(FakePlumber, 'wait_for_gamepad', return_value=False):
            self.assertEqual(self.run_with(plumber, 'restore'), 1)
        self.assertEqual([path.name for path in Path(self.tmp.name).iterdir()], [plumber.device.setting_id])
        self.assertEqual(self.run_with(plumber, 'restore'), 0)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_unknown_type_is_refused(self):
        self.assertEqual(self.run_with(FakePlumber(['xbox-elite']), 'game', 'n64'), 2)


if __name__ == '__main__':
    unittest.main()
