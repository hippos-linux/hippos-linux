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


class PrintedLabelTests(unittest.TestCase):
    def test_bottom_button_reads_a_on_most_pads(self):
        self.assertEqual(es.printed_label('b', 0x045e), 'A')
        self.assertEqual(es.printed_label('a', 0x045e), 'B')

    def test_nintendo_pads_keep_their_layout(self):
        self.assertEqual(es.printed_label('b', es.NINTENDO_VENDOR), 'B')
        self.assertEqual(es.printed_label('a', es.NINTENDO_VENDOR), 'A')


class OkAndBackTests(unittest.TestCase):
    def settings(self, text):
        import tempfile
        handle = tempfile.NamedTemporaryFile('w', suffix='.cfg', delete=False)
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    def test_es_confirms_with_b_by_default(self):
        es.ES_SETTINGS = self.settings('<config><bool name="LoadEmptySystems" value="false" /></config>')
        self.assertEqual(es.ok_and_back(), ('b', 'a'))

    def test_swap_validate_and_back_setting(self):
        es.ES_SETTINGS = self.settings('<config><bool name="InvertButtons" value="true" /></config>')
        self.assertEqual(es.ok_and_back(), ('a', 'b'))


if __name__ == '__main__':
    unittest.main()
