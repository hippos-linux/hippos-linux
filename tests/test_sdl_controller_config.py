import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_shared as shared
from hippos_es_input import ControllerInfo

ELITE = '030010f85e040000000b000001000000'
ELITE_WITHOUT_CRC = '030000005e040000000b000001000000'


def mapping_lines(*controllers):
    with mock.patch.object(shared, '_load_es_input_configs', return_value=[]), \
            mock.patch.object(shared, '_pick_es_profile', return_value=mock.Mock(device_name='Pad')), \
            mock.patch.object(shared, '_sdl_controller_mapping', return_value=[('a', 'b0')]):
        return shared.generate_sdl_game_controller_config(list(controllers)).splitlines()


class SdlControllerConfigTests(unittest.TestCase):
    def test_guid_with_crc_also_gets_a_line_without_it(self):
        lines = mapping_lines(ControllerInfo(player=1, guid=ELITE, name='Xbox Elite'))
        self.assertEqual([line.split(',')[0] for line in lines], [ELITE, ELITE_WITHOUT_CRC])
        self.assertEqual(lines[0].split(',')[1:], lines[1].split(',')[1:])

    def test_guid_without_crc_gets_one_line(self):
        lines = mapping_lines(ControllerInfo(player=1, guid=ELITE_WITHOUT_CRC, name='Xbox 360'))
        self.assertEqual([line.split(',')[0] for line in lines], [ELITE_WITHOUT_CRC])

    def test_same_controller_twice_is_listed_once(self):
        pad = ControllerInfo(player=1, guid=ELITE, name='Xbox Elite')
        self.assertEqual(len(mapping_lines(pad, ControllerInfo(player=2, guid=ELITE, name='Xbox Elite'))), 2)


if __name__ == '__main__':
    unittest.main()
