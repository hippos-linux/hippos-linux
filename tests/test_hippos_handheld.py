import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = (Path(__file__).resolve().parent.parent
               / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos' / 'hippos-handheld')


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


if __name__ == '__main__':
    unittest.main()
