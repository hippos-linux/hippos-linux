import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import hippos_updates  # noqa: E402


def update(kind, name, installed='1', available='2'):
    return {'kind': kind, 'name': name, 'installed': installed, 'available': available}


class GroupingTests(unittest.TestCase):
    def test_fixes_share_one_notification_and_emulators_get_their_own(self):
        groups = hippos_updates.offered([update('emulator', 'ares'), update('emulator', 'duckstation'),
                                         update('patch', 'fix-1'), update('patch', 'fix-2')])
        self.assertEqual([[u['name'] for u in group] for group in groups], [['fix-1', 'fix-2'], ['ares'], ['duckstation']])

    def test_parts_of_a_new_hippos_version_are_not_announced_separately(self):
        groups = hippos_updates.worth_announcing(hippos_updates.offered(
            [update('system', 'HippOS', '0.6.12', '0.6.13'), update('frontend', 'emulationstation'),
             update('patch', 'fix-1'), update('emulator', 'ares')]))
        self.assertEqual([group[0]['kind'] for group in groups], ['system', 'emulator'])

    def test_emulators_that_are_not_installed_are_not_offered(self):
        self.assertEqual(hippos_updates.offered([update('emulator', 'xemu', installed='')]), [])


class WordingTests(unittest.TestCase):
    def test_headlines(self):
        self.assertEqual(hippos_updates.available_headline([update('system', 'HippOS', '0.6.12', '0.6.13')]),
                         'HippOS 0.6.13 is available')
        self.assertEqual(hippos_updates.available_headline([update('frontend', 'emulationstation')]),
                         'EmulationStation update is available')
        self.assertEqual(hippos_updates.available_headline([update('patch', 'fix-1')]),
                         'Fixes for this version are available')

    def test_a_republished_build_says_new_build(self):
        self.assertEqual(hippos_updates.versions([update('emulator', 'ares', 'v148', 'v148')]), 'v148 · new build')


if __name__ == '__main__':
    unittest.main()
