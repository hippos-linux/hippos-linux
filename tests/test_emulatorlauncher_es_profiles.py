import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos'))

import emulatorlauncher_shared as shared  # noqa: E402
import hippos_es_input  # noqa: E402

PLAYERS = '''<inputList>
  <inputConfig type="joystick" deviceName="r36s_Gamepad" deviceGUID="19003982010000008811000088010000">
    <input name="a" type="button" id="1" value="1" />
  </inputConfig>
</inputList>'''
INSTALLED = '''<inputList>
  <inputConfig type="joystick" deviceName="Xbox 360 Controller" deviceGUID="030000005e0400008e02000014010000">
    <input name="a" type="button" id="0" value="1" />
  </inputConfig>
  <inputConfig type="joystick" deviceName="r36s_Gamepad" deviceGUID="19003982010000008811000088010000">
    <input name="a" type="button" id="5" value="1" />
  </inputConfig>
</inputList>'''


def controller(name, guid, path=''):
    return shared.ControllerInfo(player=1, index=0, guid=guid, name=name, device_path=path)


class ESProfilesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.players = Path(tmp.name) / 'es_input_players.cfg'
        self.installed = Path(tmp.name) / 'es_input.cfg'
        self.players.write_text(PLAYERS)
        self.installed.write_text(INSTALLED)
        for name, value in (('ES_PLAYERS_INPUT', self.players), ('ES_INPUT_FILES', (self.installed,)),
                            ('PARSED_CACHE_DIR', Path(tmp.name) / 'cache')):
            patcher = mock.patch.object(hippos_es_input, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        parse = mock.patch.object(hippos_es_input, '_parse_es_input_file',
                                  wraps=hippos_es_input._parse_es_input_file.__wrapped__)
        self.parse = parse.start()
        self.addCleanup(parse.stop)

    def parsed_files(self):
        return [call.args[0] for call in self.parse.call_args_list]

    def test_exact_match_in_players_file_skips_installed_file(self):
        profile = shared._pick_es_profile(shared._load_es_input_configs(),
                                          controller('r36s_Gamepad', '19003982010000008811000088010000'))
        self.assertEqual(profile.inputs['a'].code, 1)
        self.assertEqual(self.parsed_files(), [self.players])

    def test_controller_missing_from_players_file_uses_installed_file(self):
        profile = shared._pick_es_profile(shared._load_es_input_configs(),
                                          controller('Xbox 360 Controller', '030000005e0400008e02000014010000'))
        self.assertEqual(profile.device_name, 'Xbox 360 Controller')
        self.assertEqual(self.parsed_files(), [self.players, self.installed])

    def test_guid_match_in_installed_file_beats_name_match_in_players_file(self):
        profile = shared._pick_es_profile(shared._load_es_input_configs(),
                                          controller('r36s_Gamepad', '030000005e0400008e02000014010000'))
        self.assertEqual(profile.device_name, 'Xbox 360 Controller')

    def test_no_players_file_falls_back_to_first_installed_profile(self):
        self.players.unlink()
        profile = shared._pick_es_profile(shared._load_es_input_configs(), controller('Unknown pad', 'ffff'))
        self.assertEqual(profile.device_name, 'Xbox 360 Controller')


class ParsedCacheTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.installed = Path(tmp.name) / 'es_input.cfg'
        self.installed.write_text(INSTALLED)
        patcher = mock.patch.object(hippos_es_input, 'PARSED_CACHE_DIR', Path(tmp.name) / 'cache')
        patcher.start()
        self.addCleanup(patcher.stop)

    def parse(self):
        return hippos_es_input._parse_es_input_file.__wrapped__(self.installed, self.installed.stat().st_mtime_ns)

    def test_second_parse_reads_the_cache_not_the_xml(self):
        first = self.parse()
        with mock.patch.object(hippos_es_input, '_parse_es_input_xml') as xml:
            second = self.parse()
        xml.assert_not_called()
        self.assertEqual([p.device_name for p in second], [p.device_name for p in first])
        self.assertEqual(second[1].normalized_name, 'r36sgamepad')

    def test_changed_file_is_parsed_again(self):
        self.parse()
        self.installed.write_text(INSTALLED.replace('Xbox 360 Controller', 'Xbox One Controller'))
        os.utime(self.installed, ns=(1, 1))
        self.assertEqual(self.parse()[0].device_name, 'Xbox One Controller')


if __name__ == '__main__':
    unittest.main()
