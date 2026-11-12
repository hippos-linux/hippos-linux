import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

from evdev import ecodes  # noqa: E402

import hippos_es_buttons as es  # noqa: E402

PAD_KEYS = {ecodes.BTN_SOUTH, ecodes.BTN_EAST, ecodes.BTN_NORTH, ecodes.BTN_WEST,
            ecodes.BTN_TL, ecodes.BTN_TR, ecodes.BTN_SELECT, ecodes.BTN_START, ecodes.BTN_MODE}
ES_INPUT = '''<inputList>
  <inputConfig type="joystick" deviceName="Zikway HID gamepad">
    <input name="a" type="button" id="0" value="1" />
    <input name="b" type="button" id="1" value="1" />
    <input name="hotkey" type="button" id="8" value="1" />
  </inputConfig>
</inputList>'''


class ButtonNameTests(unittest.TestCase):
    def test_es_mapping_names_the_buttons(self):
        maps = es.joystick_button_maps(ET.fromstring(ES_INPUT))
        names = es.button_names('Zikway HID gamepad', PAD_KEYS, maps)
        self.assertEqual(names[ecodes.BTN_SOUTH], 'a')
        self.assertEqual(names[ecodes.BTN_EAST], 'b')
        self.assertEqual(names[ecodes.BTN_MODE], 'hotkey')

    def test_unmapped_pad_uses_the_es_default_layout(self):
        names = es.button_names('Other pad', PAD_KEYS, {})
        self.assertEqual(names[ecodes.BTN_EAST], 'a')
        self.assertEqual(names[ecodes.BTN_SOUTH], 'b')
        self.assertEqual(names[ecodes.BTN_TL], 'pageup')


if __name__ == '__main__':
    unittest.main()
