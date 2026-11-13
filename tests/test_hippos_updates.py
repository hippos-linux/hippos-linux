import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import hippos_updates  # noqa: E402


def update(kind, name, installed='1', available='2'):
    return {'kind': kind, 'name': name, 'installed': installed, 'available': available}


class SummaryTests(unittest.TestCase):
    def test_system_update_leads_the_headline(self):
        updates = [update('emulator', 'ares'), update('system', 'HippOS', '0.6.12', '0.6.13')]
        self.assertEqual(hippos_updates.headline(updates), 'HippOS 0.6.13 is available')

    def test_components_are_counted(self):
        updates = [update('frontend', 'emulationstation'), update('emulator', 'ares'),
                   update('emulator', 'duckstation'), update('patch', 'fix-1'), update('patch', 'fix-2')]
        self.assertEqual(hippos_updates.summary(updates), 'EmulationStation, 2 emulators, 2 fixes')

    def test_emulators_that_are_not_installed_are_not_offered(self):
        self.assertFalse(hippos_updates.is_offered(update('emulator', 'xemu', installed='')))
        self.assertTrue(hippos_updates.is_offered(update('frontend', 'emulationstation', installed='')))

    def test_the_same_updates_give_the_same_key_in_any_order(self):
        first, second = update('emulator', 'ares'), update('patch', 'fix-1')
        self.assertEqual(hippos_updates.notification_key([first, second]),
                         hippos_updates.notification_key([second, first]))


if __name__ == '__main__':
    unittest.main()
